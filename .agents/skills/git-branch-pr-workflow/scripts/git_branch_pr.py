#!/usr/bin/env python3
"""
Utilitário de Automação Git: Detecção de branch principal, criação de branches de feature/fix e preparação de PRs.
Compatível com Windows, macOS e Linux.
"""

import argparse
import re
import subprocess
import sys
from typing import Optional, Tuple


def run_git_cmd(args: list[str]) -> Tuple[int, str, str]:
    """Executa um comando git e retorna (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def detect_primary_branch() -> str:
    """
    Identifica se a branch principal do repositório é 'main' ou 'master'.
    Verifica origin/HEAD, branches remotas e branches locais.
    """
    # 1. Tenta obter pelo origin/HEAD
    code, out, _ = run_git_cmd(["symbolic-ref", "refs/remotes/origin/HEAD"])
    if code == 0 and out:
        branch = out.split("/")[-1]
        if branch:
            return branch

    # 2. Tenta verificar se refs/remotes/origin/main ou origin/master existem
    code, _, _ = run_git_cmd(["rev-parse", "--verify", "origin/main"])
    if code == 0:
        return "main"

    code, _, _ = run_git_cmd(["rev-parse", "--verify", "origin/master"])
    if code == 0:
        return "master"

    # 3. Tenta verificar branches locais
    code, _, _ = run_git_cmd(["rev-parse", "--verify", "main"])
    if code == 0:
        return "main"

    code, _, _ = run_git_cmd(["rev-parse", "--verify", "master"])
    if code == 0:
        return "master"

    # Padrão seguro caso não encontre
    return "main"


def get_repo_github_info() -> Optional[Tuple[str, str]]:
    """Extrai (owner, repo) a partir da URL do remote 'origin'."""
    code, out, _ = run_git_cmd(["remote", "get-url", "origin"])
    if code != 0 or not out:
        return None

    url = out.strip()
    # Padrões HTTPS e SSH
    match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?", url)
    if match:
        owner = match.group(1)
        repo = match.group(2)
        return owner, repo
    return None


def get_current_branch() -> str:
    """Retorna o nome da branch atual."""
    code, out, _ = run_git_cmd(["branch", "--show-current"])
    if code == 0 and out:
        return out
    return "HEAD"


def is_working_tree_clean() -> bool:
    """Verifica se há arquivos modificados ou não rastreados."""
    code, out, _ = run_git_cmd(["status", "--porcelain"])
    return code == 0 and len(out.strip()) == 0


def create_branch(branch_name: str, base_branch: Optional[str] = None, force: bool = False) -> bool:
    """Atualiza a branch base e cria uma nova branch a partir dela."""
    if not base_branch:
        base_branch = detect_primary_branch()

    if not force and not is_working_tree_clean():
        print(
            "AVISO: Há alterações não commitadas na árvore de trabalho.",
            file=sys.stderr
        )
        print(
            "Faça commit, stash ou use --force para ignorar.",
            file=sys.stderr
        )
        return False

    print(f"Detectada branch principal: '{base_branch}'")
    print(f"Atualizando referências remotas de 'origin/{base_branch}'...")
    run_git_cmd(["fetch", "origin", base_branch])

    # Criação da nova branch a partir de origin/<base> (ou base local caso não exista origin)
    start_point = f"origin/{base_branch}"
    code, _, _ = run_git_cmd(["rev-parse", "--verify", start_point])
    if code != 0:
        start_point = base_branch

    print(f"Criando e mudando para a branch '{branch_name}' a partir de '{start_point}'...")
    code, out, err = run_git_cmd(["checkout", "-b", branch_name, start_point])
    if code != 0:
        print(f"Erro ao criar branch: {err}", file=sys.stderr)
        return False

    print(f"Branch '{branch_name}' criada com sucesso!")
    return True


def generate_pr_url(branch_name: Optional[str] = None, base_branch: Optional[str] = None) -> str:
    """Gera o link de criação de Pull Request no GitHub."""
    if not branch_name:
        branch_name = get_current_branch()
    if not base_branch:
        base_branch = detect_primary_branch()

    info = get_repo_github_info()
    if not info:
        return f"Compare: <base:{base_branch}> ... <head:{branch_name}>"

    owner, repo = info
    return f"https://github.com/{owner}/{repo}/compare/{base_branch}...{branch_name}?expand=1"


def main():
    parser = argparse.ArgumentParser(
        description="Utilitário de workflow Git para criação de branch de PR a partir da main/master."
    )
    subparsers = parser.add_subparsers(dest="command")

    # Comando: detect
    subparsers.add_parser("detect", help="Detecta qual é a branch principal (main ou master)")

    # Comando: create
    create_parser = subparsers.add_parser("create", help="Cria uma nova branch a partir da branch principal")
    create_parser.add_argument("name", help="Nome da nova branch (ex: feat/nova-tela, fix/bug-calculo)")
    create_parser.add_argument("--base", help="Branch base (se omitido, detecta main ou master)")
    create_parser.add_argument("--force", action="store_true", help="Ignora working tree suja")

    # Comando: pr-url
    pr_parser = subparsers.add_parser("pr-url", help="Gera o link de comparação e abertura de PR no GitHub")
    pr_parser.add_argument("--branch", help="Nome da branch (padrão: branch atual)")
    pr_parser.add_argument("--base", help="Branch base (padrão: main ou master)")

    # Comando: status
    subparsers.add_parser("status", help="Exibe o status atual e informações de branch")

    args = parser.parse_args()

    if args.command == "detect":
        print(detect_primary_branch())

    elif args.command == "create":
        success = create_branch(args.name, base_branch=args.base, force=args.force)
        sys.exit(0 if success else 1)

    elif args.command == "pr-url":
        url = generate_pr_url(branch_name=args.branch, base_branch=args.base)
        print(url)

    elif args.command == "status":
        primary = detect_primary_branch()
        current = get_current_branch()
        clean = is_working_tree_clean()
        gh_info = get_repo_github_info()
        print(f"Branch atual: {current}")
        print(f"Branch principal: {primary}")
        print(f"Working tree limpa: {'Sim' if clean else 'Não'}")
        if gh_info:
            print(f"Repositório GitHub: {gh_info[0]}/{gh_info[1]}")
            if current != primary:
                print(f"URL de PR: {generate_pr_url(current, primary)}")
    else:
        # Se nenhum comando informado, exibe detecção
        print(f"Branch principal detectada: {detect_primary_branch()}")


if __name__ == "__main__":
    main()
