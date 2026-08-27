"""Cliente mínimo de la API de GitHub sobre stdlib.

El token se obtiene de `gh auth token` en runtime; nunca se persiste (AGENTS.md §5).
El cliente distingue lecturas (siempre se ejecutan) de escrituras (solo con
`apply=True`), de modo que el dry-run sea el comportamiento por defecto.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import config


class GitHubError(Exception):
    def __init__(self, status: int, message: str, url: str = ""):
        super().__init__(f"HTTP {status} en {url}: {message}")
        self.status = status
        self.message = message
        self.url = url


class ScopeError(Exception):
    """Al token le faltan scopes; fallar antes de crear nada."""


def get_token() -> str:
    """Lee el token desde `gh`, para no manejar credenciales propias."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "No se encontró el ejecutable `gh`. Instala GitHub CLI."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "`gh auth token` falló. Ejecuta `gh auth login` primero.\n"
            f"{exc.stderr.strip()}"
        ) from exc

    token = result.stdout.strip()
    if not token:
        raise RuntimeError("`gh auth token` no devolvió un token.")
    return token


class GitHubClient:
    def __init__(self, token: str, apply: bool = False, log=print):
        self.token = token
        self.apply = apply
        self.log = log

    # -- transporte -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        soft_statuses: tuple[int, ...] = (),
        accept: str = "application/vnd.github+json",
    ):
        """Devuelve (status, payload). `soft_statuses` no levanta excepción."""
        url = path if path.startswith("http") else f"{config.API_ROOT}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None

        for intento in range(1, config.MAX_RETRIES + 1):
            request = urllib.request.Request(url, data=data, method=method)
            request.add_header("Authorization", f"Bearer {self.token}")
            request.add_header("Accept", accept)
            request.add_header("X-GitHub-Api-Version", config.API_VERSION)
            request.add_header("User-Agent", config.USER_AGENT)
            if data is not None:
                request.add_header("Content-Type", "application/json")

            try:
                with urllib.request.urlopen(request) as response:
                    raw = response.read()
                    payload = json.loads(raw) if raw else None
                    return response.status, payload
            except urllib.error.HTTPError as error:
                raw = error.read()
                try:
                    payload = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    payload = {"message": raw.decode("utf-8", "replace")}

                if error.code in soft_statuses:
                    return error.code, payload

                if self._should_retry(error) and intento < config.MAX_RETRIES:
                    espera = self._retry_delay(error, intento)
                    self.log(
                        f"    · HTTP {error.code}; reintento {intento}/"
                        f"{config.MAX_RETRIES - 1} en {espera:.0f}s"
                    )
                    time.sleep(espera)
                    continue

                mensaje = (payload or {}).get("message", "sin detalle")
                errores = (payload or {}).get("errors")
                if errores:
                    mensaje = f"{mensaje} — {json.dumps(errores, ensure_ascii=False)}"
                raise GitHubError(error.code, mensaje, url)
            except urllib.error.URLError as error:
                if intento < config.MAX_RETRIES:
                    espera = config.BACKOFF_BASE_SECONDS * (2 ** (intento - 1))
                    self.log(f"    · error de red ({error.reason}); reintento en {espera:.0f}s")
                    time.sleep(espera)
                    continue
                raise

        raise GitHubError(0, "se agotaron los reintentos", url)

    @staticmethod
    def _should_retry(error: urllib.error.HTTPError) -> bool:
        if error.code in (429, 500, 502, 503, 504):
            return True
        # 403 solo si es rate limit / abuse detection, no si es falta de permisos.
        if error.code == 403:
            restante = error.headers.get("X-RateLimit-Remaining")
            return error.headers.get("Retry-After") is not None or restante == "0"
        return False

    @staticmethod
    def _retry_delay(error: urllib.error.HTTPError, intento: int) -> float:
        retry_after = error.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        reset = error.headers.get("X-RateLimit-Reset")
        if reset and reset.isdigit():
            return max(1.0, float(reset) - time.time())
        return config.BACKOFF_BASE_SECONDS * (2 ** (intento - 1))

    def _write(self, method: str, path: str, body: dict | None = None, **kwargs):
        """Escritura: en dry-run no toca la red."""
        if not self.apply:
            return None, None
        return self._request(method, path, body, **kwargs)

    # -- autenticación --------------------------------------------------------

    def token_scopes(self) -> list[str] | None:
        """Scopes del token clásico, o None si es fine-grained (no expone el header)."""
        request = urllib.request.Request(f"{config.API_ROOT}/user", method="GET")
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", config.USER_AGENT)
        try:
            with urllib.request.urlopen(request) as response:
                header = response.headers.get("X-OAuth-Scopes")
        except urllib.error.HTTPError as error:
            raise GitHubError(error.code, "no se pudo validar el token", "/user")
        if header is None:
            return None
        return [s.strip() for s in header.split(",") if s.strip()]

    def check_scopes(self, required=config.REQUIRED_SCOPES) -> list[str]:
        """Devuelve los scopes faltantes; lista vacía si está todo bien."""
        scopes = self.token_scopes()
        if scopes is None:
            return []  # token fine-grained: no se puede verificar por header
        faltantes = []
        for scope in required:
            if scope in scopes:
                continue
            # `admin:org` implica `read:org`/`write:org`; `repo` implica sus hijos.
            if scope == "repo" and any(s.startswith("repo") for s in scopes):
                continue
            faltantes.append(scope)
        return faltantes

    # -- usuarios -------------------------------------------------------------

    def user_exists(self, username: str) -> bool:
        status, _ = self._request(
            "GET", f"/users/{urllib.parse.quote(username)}", soft_statuses=(404,)
        )
        return status == 200

    # -- repositorios ---------------------------------------------------------

    def repo_exists(self, repo: str) -> bool:
        status, _ = self._request(
            "GET", f"/repos/{config.ORG}/{repo}", soft_statuses=(404,)
        )
        return status == 200

    def create_from_template(self, repo: str, description: str) -> dict | None:
        body = {
            "owner": config.ORG,
            "name": repo,
            "description": description,
            "private": config.REPO_PRIVATE,
            "include_all_branches": False,
        }
        _, payload = self._write(
            "POST",
            f"/repos/{config.TEMPLATE_OWNER}/{config.TEMPLATE_REPO}/generate",
            body,
        )
        return payload

    def wait_for_repo(self, repo: str, timeout: float = config.TEMPLATE_PROPAGATION_TIMEOUT):
        """Tras `generate`, el repo puede devolver 404 unos segundos."""
        if not self.apply:
            return
        limite = time.time() + timeout
        while time.time() < limite:
            if self.repo_exists(repo):
                return
            time.sleep(2.0)
        raise GitHubError(404, f"{repo} no quedó disponible tras {timeout:.0f}s")

    # -- colaboradores --------------------------------------------------------

    def collaborator_state(self, repo: str, username: str) -> str:
        """`collaborator`, `invited` o `none`."""
        status, _ = self._request(
            "GET",
            f"/repos/{config.ORG}/{repo}/collaborators/{urllib.parse.quote(username)}",
            soft_statuses=(404,),
        )
        if status == 204:
            return "collaborator"

        _, invitaciones = self._request(
            "GET", f"/repos/{config.ORG}/{repo}/invitations?per_page=100"
        )
        for invitacion in invitaciones or []:
            invitee = (invitacion.get("invitee") or {}).get("login", "")
            if invitee.lower() == username.lower():
                return "invited"
        return "none"

    def add_collaborator(self, repo: str, username: str, permission: str):
        self._write(
            "PUT",
            f"/repos/{config.ORG}/{repo}/collaborators/{urllib.parse.quote(username)}",
            {"permission": permission},
        )

    # -- teams ----------------------------------------------------------------

    def team_repo_permission(self, repo: str, team: str | None = None) -> str | None:
        """Permiso actual del team sobre el repo, o None si no tiene acceso."""
        team = team or config.TEAM_SLUG
        # Sin este media type el endpoint responde 204 sin cuerpo y no se puede
        # saber qué permiso tiene el team, solo que tiene alguno.
        status, payload = self._request(
            "GET",
            f"/orgs/{config.ORG}/teams/{team}/repos/{config.ORG}/{repo}",
            soft_statuses=(404,),
            accept="application/vnd.github.v3.repository+json",
        )
        if status == 404:
            return None
        if not payload:
            return "unknown"
        rol = payload.get("role_name")
        if rol:
            return rol
        permisos = payload.get("permissions") or {}
        for nivel in ("admin", "maintain", "push", "triage", "pull"):
            if permisos.get(nivel):
                return nivel
        return "unknown"

    def add_team_to_repo(self, repo: str, permission: str, team: str | None = None):
        team = team or config.TEAM_SLUG
        self._write(
            "PUT",
            f"/orgs/{config.ORG}/teams/{team}/repos/{config.ORG}/{repo}",
            {"permission": permission},
        )

    # -- issues ---------------------------------------------------------------

    def issue_exists(self, repo: str, title: str) -> bool:
        _, issues = self._request(
            "GET", f"/repos/{config.ORG}/{repo}/issues?state=all&per_page=100"
        )
        return any((i.get("title") or "") == title for i in issues or [])

    def create_issue(self, repo: str, title: str, body: str) -> dict | None:
        _, payload = self._write(
            "POST", f"/repos/{config.ORG}/{repo}/issues", {"title": title, "body": body}
        )
        return payload
