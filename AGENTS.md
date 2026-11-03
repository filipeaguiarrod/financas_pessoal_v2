# Diretrizes do Repositório - Antigravity

Este repositório possui regras obrigatórias de governança para qualquer agente de IA que atue no código.

---

## 1. Planejamento Obrigatório Antes de Codificar
- **NUNCA faça alterações de código, crie novos arquivos de código ou aplique correções sem aprovação prévia**.
- Antes de modificar qualquer linha de código:
  1. Realize **apenas pesquisa e leitura** dos arquivos relevantes.
  2. Crie ou atualize o artefato de plano de implementação (`implementation_plan.md`) com `RequestFeedback: true` e `UserFacing: true`.
  3. No plano, descreva claramente o objetivo, os arquivos a serem criados/modificados e a estratégia de testes/validação.
  4. **PARE imediatamente** e aguarde a aprovação explícita do usuário (botão *Proceed* ou confirmação textual) antes de qualquer escrita de código.

---

## 2. Fluxo Git para Sugestões de Código e Pull Requests
- Sempre que houver sugestão, adição, refatoração ou correção de código aprovada:
  1. **NÃO altere o código diretamente na branch atual sem antes criar a branch adequada**.
  2. Utilize a skill `git-branch-pr-workflow` ou o utilitário `.agents/skills/git-branch-pr-workflow/scripts/git_branch_pr.py`.
  3. **Identificação da branch principal**: Verifique se o repositório utiliza `main` ou `master` como branch padrão.
  4. **Criação da branch**: Crie uma nova branch a partir da branch principal atualizada (`origin/main` ou `origin/master`), utilizando prefixos semânticos:
     - `feat/<nome-da-funcionalidade>` para novas funcionalidades
     - `fix/<descricao-do-bug>` para correções
     - `refactor/<alvo>` para refatorações
  5. **Implementação**: Aplique as alterações e valide com testes.
  6. **Commit e Push**:
     - Realize commits com mensagens convencionais (`feat: ...`, `fix: ...`, etc.).
     - Envie para o remoto: `git push -u origin <nome-da-branch>`.
  7. **Pull Request**:
     - Se o utilitário GitHub CLI (`gh`) estiver disponível, execute `gh pr create`.
     - Caso contrário, gere o link direto de comparação do GitHub (`https://github.com/<owner>/<repo>/compare/<primary>...<branch>?expand=1`) e forneça o título e corpo formatados para o usuário abrir o PR.

---

## 3. Política de Execução de Comandos e Salvaguardas de Segurança

### Execução Automática Habilitada
- Todos os comandos rotineiros de desenvolvimento (inspeção, testes, compilação, `git status/diff/fetch/checkout/commit/push`, instalação de pacotes `pip/uv/npm`, execução de linters e scripts de verificação) devem ser executados de forma automática e proativa.

### Restrições Rígidas de Segurança e Deleção
- **Comandos de Deleção / Remoção**:
  - Comandos como `rm`, `Remove-Item`, `del`, `rmdir`, `git clean -f`, `git reset --hard` ou scripts que deletem arquivos/pastas **NUNCA** devem ser executados automaticamente.
  - O agente DEVE solicitar autorização prévia e explícita do usuário no chat antes de disparar qualquer comando de remoção.
- **Segurança de Credenciais e Dados Sensíveis**:
  - NUNCA imprima no terminal, registre em logs ou exiba chaves de API, senhas, tokens ou o conteúdo integral de arquivos `.env` e credenciais.
- **Operações Destrutivas em Banco de Dados**:
  - Proibido executar comandos como `DROP TABLE`, `DROP DATABASE`, `TRUNCATE` ou `DELETE` sem cláusula `WHERE` sem confirmação explícita do usuário.
