# ⏱️ Clockify Pro — Rastreador de Tempo, Projetos & Auto-Tracker AutoCAD

Sistema completo de gestão de horas e apontamento de projetos inspirado no Clockify, com suporte híbrido para operação em nuvem (Vercel) e integração desktop com rastreamento automático de janelas ativas e arquivos `.dwg` do AutoCAD.

---

## 🌟 Funcionalidades

1. **⏱️ Rastreador de Tempo (Time Tracker):**
   - Modo cronômetro em tempo real (INICIAR / PARAR com precisão ao segundo).
   - Modo manual com seleção de horário início/fim e data.
   - Apontamento atrelado a Projeto, Cliente, Etiqueta e status Faturável ($).
   - Agrupamento visual por dia com cálculo acumulado de horas.
   - Botão Play (▶) para retomar qualquer tarefa com 1 clique.

2. **📅 Planilha de Horas (Timesheet Semanal):**
   - Lançamento em grade rápida de horas trabalhadas por projeto.

3. **📊 Painel & Relatórios Executivos:**
   - Métricas em tempo real: Total de Horas, Horas Faturáveis e Valor Total a Faturar (R$).
   - Gráfico de barras com distribuição de tempo por projeto.
   - Filtros dinâmicos por Projeto, Cliente, Etiqueta e Intervalo de Datas.
   - 📥 **Exportação Direta em Excel (.CSV)** formatado em UTF-8 com separador e BOM.

4. **📁 Gestão Completa:**
   - **Projetos:** Código, nome, cliente, cor visual, valor/hora (R$) e orçamento de horas.
   - **Clientes:** Cadastro de clientes corporativos e empresas parceiras.
   - **Equipe:** Cadastro de usuários e taxas individuais.
   - **Etiquetas:** Tags organizacionais (AutoCAD, 2D/3D, Revisão, Urgente, etc.).

5. **🤖 Auto-Rastreador AutoCAD (Desktop):**
   - Quando executado localmente via Python (`server.py`), monitora em background a janela ativa do Windows e os arquivos `.dwg` em uso.
   - Converte automaticamente eventos detectados em apontamentos de horas.

---

## 🚀 Como Executar

### 1. Operação em Nuvem (Vercel)
Acesse a aplicação diretamente pelo navegador. Todos os dados, cronômetros e relatórios são persistidos no navegador (`localStorage`) com carregamento instantâneo.

### 2. Operação Local com Auto-Rastreador AutoCAD
1. Execute o arquivo `Iniciar_ClockIn.bat` (ou execute `python server.py`).
2. O servidor local iniciará na porta `5050` e abrirá o painel no navegador padrão.
3. O painel conectará automaticamente ao banco local SQLite (`clockify_local.db`).
