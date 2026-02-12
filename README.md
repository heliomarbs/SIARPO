# Sistema Especialista NR-1 — Riscos Psicossociais (GRO / PGR)

Este projeto implementa um **sistema especialista de apoio à decisão** para análise técnica de riscos psicossociais ocupacionais, alinhado à **NR-1**, **GRO** e **PGR**.

O sistema processa automaticamente respostas coletadas via **Google Forms → Google Sheets**, calcula indicadores normalizados (0–100), identifica padrões de risco/impacto e produz:

- um **JSON premium (IA-ready)** para análise por LLM (ChatGPT/Agentes)
- um **relatório técnico em texto** para uso em consultorias e apresentações
- um **prompt pronto** para rodar análises padronizadas com consistência

> ⚠️ Importante: este sistema **não diagnostica clinicamente**, **não emite laudos**, e deve ser usado como **ferramenta de apoio**, com validação técnica humana.

---

## 🎯 Problema que resolve
Consultorias de NR-1/GRO/PGR frequentemente enfrentam:
- altos volumes de respostas
- inconsistência de interpretação entre consultores
- dificuldade em justificar tecnicamente priorizações
- fragilidade em rastreabilidade (dados → decisão)
- pouca conexão entre risco psicossocial e impacto financeiro (ROI)

Este sistema padroniza o cálculo, interpretação e entrega.

---

## 🧠 Modelo lógico (alto nível)

### Camadas do modelo:
1. **Risco (probabilidade)**
   - Dimensões R1…R6 (normalizadas 0–100)
   - Pesos por item e inversão obrigatória quando aplicável

2. **Impacto (consequência instalada)**
   - Itens G1…G6 (indicadores funcionais não clínicos)

3. **Maturidade organizacional**
   - Itens M1…M12 (governança, prevenção, canais, liderança, melhoria contínua)

4. **ROI (produtividade)**
   - Estimativa financeira baseada em perdas por produtividade
   - Fonte: folha salarial mensal total informada por RH/Diretoria

---

## 📌 Fluxo de dados
# Sistema Especialista NR-1 — Riscos Psicossociais (GRO / PGR)

Este projeto implementa um **sistema especialista de apoio à decisão** para análise técnica de riscos psicossociais ocupacionais, alinhado à **NR-1**, **GRO** e **PGR**.

O sistema processa automaticamente respostas coletadas via **Google Forms → Google Sheets**, calcula indicadores normalizados (0–100), identifica padrões de risco/impacto e produz:

- um **JSON premium (IA-ready)** para análise por LLM (ChatGPT/Agentes)
- um **relatório técnico em texto** para uso em consultorias e apresentações
- um **prompt pronto** para rodar análises padronizadas com consistência

> ⚠️ Importante: este sistema **não diagnostica clinicamente**, **não emite laudos**, e deve ser usado como **ferramenta de apoio**, com validação técnica humana.

---

## 🎯 Problema que resolve
Consultorias de NR-1/GRO/PGR frequentemente enfrentam:
- altos volumes de respostas
- inconsistência de interpretação entre consultores
- dificuldade em justificar tecnicamente priorizações
- fragilidade em rastreabilidade (dados → decisão)
- pouca conexão entre risco psicossocial e impacto financeiro (ROI)

Este sistema padroniza o cálculo, interpretação e entrega.

---

## 🧠 Modelo lógico (alto nível)

### Camadas do modelo:
1. **Risco (probabilidade)**
   - Dimensões R1…R6 (normalizadas 0–100)
   - Pesos por item e inversão obrigatória quando aplicável

2. **Impacto (consequência instalada)**
   - Itens G1…G6 (indicadores funcionais não clínicos)

3. **Maturidade organizacional**
   - Itens M1…M12 (governança, prevenção, canais, liderança, melhoria contínua)

4. **ROI (produtividade)**
   - Estimativa financeira baseada em perdas por produtividade
   - Fonte: folha salarial mensal total informada por RH/Diretoria

---

## 📌 Fluxo de dados
Google Forms
↓
Google Sheets (respostas)
↓
Pipeline Python
↓
reports/<ID>/
├── report_premium.json (IA-ready)
├── report.txt (humano / diretoria)
└── prompt_ai.txt (prompt padrão para IA)


---

## ⚙️ Execução

### 1) Configurar credenciais
Coloque o JSON do Service Account em:

secrets/google_service_account.json


### 2) Instalar dependências
```bash
pip install -r requirements.txt

