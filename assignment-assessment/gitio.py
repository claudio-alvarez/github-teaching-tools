"""Operaciones de git y de clonado sobre los repositorios de grupo.

Todo se hace con los ejecutables `git` y `gh` por subproceso: no hay
dependencias que instalar y la autenticación de los repos privados la resuelve
`gh`, igual que en `assignment-preparation` (el token nunca se escribe a disco
ni aparece en una línea de comandos).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """Un comando de git o gh falló. Un grupo caído no aborta a los demás."""

    def __init__(self, comando: list[str], stderr: str):
        mostrado = " ".join(comando[:4])
        super().__init__(f"`{mostrado}…` falló: {stderr.strip() or 'sin detalle'}")
        self.comando = comando
        self.stderr = stderr.strip()


@dataclass(frozen=True)
class Commit:
    sha: str
    fecha_iso: str
    autor: str
    asunto: str


def _run(comando: list[str], cwd: Path | None = None, check: bool = True,
         timeout: float = 600) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            comando,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitError(comando, f"no se encontró el ejecutable `{comando[0]}`") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(comando, f"se agotó el tiempo ({timeout:.0f}s)") from exc
    if check and result.returncode != 0:
        raise GitError(comando, result.stderr or result.stdout)
    return result


def git(args: list[str], repo: Path | None = None, check: bool = True) -> str:
    """Corre git y devuelve stdout sin espacios al borde."""
    base = ["git"]
    if repo is not None:
        base += ["-C", str(repo)]
    return _run(base + args, check=check).stdout.strip()


def require_tools(usa_gh: bool = True) -> list[str]:
    """Nombres de las herramientas que faltan en el PATH."""
    faltan = []
    for nombre, args in (("git", ["--version"]), ("gh", ["--version"])):
        if nombre == "gh" and not usa_gh:
            continue
        try:
            _run([nombre] + args, check=True, timeout=30)
        except GitError:
            faltan.append(nombre)
    return faltan


def is_repo(path: Path) -> bool:
    if not (path / ".git").exists():
        return False
    result = _run(["git", "-C", str(path), "rev-parse", "--git-dir"], check=False)
    return result.returncode == 0


def clone(org: str, repo: str, dest: Path) -> None:
    """Clona con `gh`, que resuelve la autenticación de los repos privados."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["gh", "repo", "clone", f"{org}/{repo}", str(dest)], timeout=1800)


def origin_url(repo: Path) -> str:
    return git(["remote", "get-url", "origin"], repo, check=False)


def fetch(repo: Path) -> None:
    git(["fetch", "--prune", "--tags", "origin"], repo)


def is_dirty(repo: Path) -> bool:
    """Hay cambios sin commitear en archivos versionados.

    Los archivos sin versionar se ignoran a propósito: un `__pycache__` o un
    `target/` que quedó de ejecutar el código del grupo no se pierde en un
    checkout, y bloquear la actualización por eso solo estorba.
    """
    return bool(git(["status", "--porcelain", "--untracked-files=no"], repo))


def default_branch(repo: Path) -> str:
    """Rama por defecto del remoto; `main` si el remoto no la declara."""
    ref = git(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo, check=False)
    if ref.startswith("refs/remotes/origin/"):
        return ref.rsplit("/", 1)[-1]
    # Repos clonados antes de que el remoto fijara HEAD: preguntar al remoto.
    salida = git(["remote", "show", "origin"], repo, check=False)
    for linea in salida.splitlines():
        if "HEAD branch:" in linea:
            rama = linea.split(":", 1)[1].strip()
            if rama and rama != "(unknown)":
                return rama
    return "main"


def resolve(repo: Path, rev: str) -> str:
    """SHA completo de una revisión, o cadena vacía si no existe."""
    return git(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
               repo, check=False)


def last_commit_before(repo: Path, rev: str, cutoff_iso: str) -> str:
    """Último commit de `rev` con fecha anterior al corte (o cadena vacía)."""
    return git(["rev-list", "-1", f"--before={cutoff_iso}", rev], repo, check=False)


def checkout(repo: Path, sha: str, rama: str | None = None) -> None:
    """Deja el clon en `sha`.

    Con rama, la reposiciona sobre el commit para que el revisor vea un nombre
    familiar; sin ella (corte por fecha) queda en HEAD desprendido, que es lo
    honesto: ese estado no corresponde a la punta de ninguna rama.
    """
    if rama:
        git(["checkout", "-B", rama, sha], repo)
    else:
        git(["checkout", "--detach", sha], repo)


def reset_hard(repo: Path) -> None:
    git(["reset", "--hard"], repo)


def root_commit(repo: Path, rev: str = "HEAD") -> str:
    """Primer commit alcanzable desde `rev`.

    En un repo creado desde un template, ese commit **es** el código base que
    recibieron los alumnos: GitHub aplasta el template en un único commit
    inicial. Por eso sirve de línea base del diff sin depender de la red.
    """
    salidas = git(["rev-list", "--max-parents=0", rev], repo, check=False).split()
    return salidas[-1] if salidas else ""


def commit_info(repo: Path, rev: str) -> Commit | None:
    salida = git(
        ["show", "-s", "--format=%H%x1f%cI%x1f%an%x1f%s", rev], repo, check=False
    )
    if not salida:
        return None
    partes = salida.split("\x1f")
    if len(partes) != 4:
        return None
    return Commit(sha=partes[0], fecha_iso=partes[1], autor=partes[2], asunto=partes[3])


def count_commits(repo: Path, desde: str, hasta: str = "HEAD") -> int:
    salida = git(["rev-list", "--count", f"{desde}..{hasta}"], repo, check=False)
    return int(salida) if salida.isdigit() else 0


def authors(repo: Path, desde: str, hasta: str = "HEAD") -> list[dict]:
    """Commits por autor en el rango, para ver el reparto del trabajo.

    Solo el nombre del autor: el correo es dato personal y no aporta acá.
    """
    salida = git(["shortlog", "-sn", "--no-merges", f"{desde}..{hasta}"],
                 repo, check=False)
    resultado = []
    for linea in salida.splitlines():
        partes = linea.strip().split("\t", 1)
        if len(partes) == 2 and partes[0].strip().isdigit():
            resultado.append({"autor": partes[1].strip(),
                              "commits": int(partes[0].strip())})
    return resultado


def diff_stat(repo: Path, desde: str, hasta: str = "HEAD") -> dict:
    """Resumen numérico del diff: archivos tocados, líneas +/-."""
    salida = git(["diff", "--numstat", f"{desde}..{hasta}"], repo, check=False)
    archivos, mas, menos = 0, 0, 0
    for linea in salida.splitlines():
        partes = linea.split("\t")
        if len(partes) != 3:
            continue
        archivos += 1
        if partes[0].isdigit():
            mas += int(partes[0])
        if partes[1].isdigit():
            menos += int(partes[1])
    return {"archivos": archivos, "insertadas": mas, "eliminadas": menos}
