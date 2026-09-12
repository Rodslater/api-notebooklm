# API NotebookLM: Podcasts Automatizados

API HTTP assíncrona baseada em FastAPI e no projeto `notebooklm-py` para geração de podcasts em áudio (resumos em Português do Brasil) a partir de arquivos de texto ou conteúdo textual direto no Google NotebookLM.

---

## 1. Visão Geral da Arquitetura

O processamento pesado de IA (leitura das fontes, elaboração do roteiro e síntese de voz dos apresentadores) é executado diretamente nos servidores do Google NotebookLM. A API atua como um orquestrador leve:
1. Recebe a solicitação HTTP com o texto ou arquivo anexado.
2. Cria um caderno temporário e adiciona o conteúdo como fonte.
3. Solicita a geração do podcast guiado para o Português do Brasil.
4. Monitora o progresso em segundo plano e realiza o download do arquivo de áudio final (`.m4a`).
5. Remove o caderno temporário do Google para não consumir a cota de cadernos da conta.
6. Notifica opcionalmente uma URL de webhook (como um endpoint do n8n) assim que o áudio estiver pronto para consumo.

Por ser assíncrona, a API retorna imediatamente um identificador de tarefa (`job_id`), evitando problemas de timeout HTTP em conexões intermediárias como Caddy e proxies reversos.

---

## 2. Autenticação com o Google NotebookLM

Para rodar em ambiente de produção (servidor sem interface gráfica) sem queda de sessão, a API utiliza o **Master Token** (`master_token.json`).

### Passo a passo para gerar o Master Token:

1. Na sua máquina local (com navegador), abra o terminal dentro deste projeto:
```powershell
.\.venv\Scripts\activate
pip install "notebooklm-py[browser,headless]"
playwright install chromium
```

2. Execute o comando de login indicando o e-mail da sua conta Google dedicada:
```powershell
notebooklm login --master-token --account seu-email-dedicado@gmail.com
```

3. O navegador será aberto para autenticação no Google. Após a confirmação, o arquivo `master_token.json` será gravado no diretório de perfis do usuário (exemplo: `~/.notebooklm/profiles/default/master_token.json`).

4. Copie o arquivo gerado para a pasta `data/auth/master_token.json` deste projeto. Em produção na VPS, a biblioteca usará o `gpsoauth` para renovar os cookies automaticamente em segundo plano, sem exigir navegador na VPS.

---

## 3. Execução Local

### Instalação de dependências:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Configuração de ambiente:
Copie o arquivo `.env.example` para `.env` e ajuste as variáveis se necessário:
```powershell
copy .env.example .env
```

### Rodar os testes:
```powershell
pytest -v
```

### Iniciar o servidor:
```powershell
python main.py
```
Acesse a documentação interativa em: `http://localhost:8000/docs`

---

## 4. Guia de Uso da API

### Endereço Base
* **Produção:** `https://podcast.rodslater.com`
* **Local:** `http://localhost:8000`

### Autenticação
Todas as rotas da API (exceto `/health`) exigem autenticação via Bearer token:
```http
Authorization: Bearer SEU_TOKEN
```
Cada token possui isolamento completo: o cliente só lista, consulta e baixa os podcasts criados pelo seu próprio token.

---

### O que você pode escolher na chamada

Ao criar um podcast, você pode personalizar o formato da conversa, a duração do áudio e as instruções dos apresentadores.

#### 1. Formato do Podcast (`format`)
Corresponde às opções de "Formato" encontradas no site do NotebookLM:

* **`deep_dive` (Análise detalhada):**
  Uma conversa animada entre dois apresentadores, que explicam e conectam temas nas suas fontes. É o formato clássico de podcast, ideal para discussões completas e aprofundadas.
* **`brief` (Resumo):**
  Uma breve visão geral para ajudar você a entender as ideias principais das suas fontes com rapidez. Ideal para recados ágeis e resumos diretos.
* **`critique` (Crítica):**
  Uma análise especializada das suas fontes, com feedback construtivo para ajudar você a aperfeiçoar seu material e apontar pontos fortes e fracos.
* **`debate` (Debate):**
  Um debate inteligente entre dois apresentadores, que trazem diferentes perspectivas e defendem pontos de vista contrastantes sobre o conteúdo.

*Se não for informado, o servidor assume o padrão configurado em `DEFAULT_AUDIO_FORMAT` (padrão: `brief`).*

#### 2. Duração do Áudio (`length`)
Corresponde às opções de "Duração" no site do NotebookLM:

* **`short` (Curto):** áudio de aproximadamente 3 a 5 minutos.
* **`default` (Padrão):** áudio de aproximadamente 8 a 12 minutos.
* **`long` (Longo):** áudio de aproximadamente 15 a 20 minutos.

*Se não for informado, o servidor assume o padrão configurado em `DEFAULT_AUDIO_LENGTH` (padrão: `default`).*

#### 3. Personalizar o Resumo em Áudio (`instructions`)
Corresponde à caixa de texto de instruções personalizadas no site do NotebookLM:

Permite orientar o estilo, o tom e os tópicos de foco dos apresentadores.
* **Exemplo de instrução:**
  `"Apresentem como um podcast bem-humorado e dinâmico entre dois podcasters em português do Brasil, comentando as reações do chat e fazendo tiradas espertas."`

*Se não for informado, o servidor assume a instrução padrão de conversa descontraída e bem-humorada em português brasileiro.*

#### 4. Idioma (`language`)
* **`pt` ou `pt-BR`:** Português do Brasil (seleciona as vozes neurais brasileiras do Google).
* **`en`:** Inglês.

---

### Resumo dos Parâmetros

| Campo | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `title` | Texto | Data/hora atual | Título descritivo do podcast ou caderno. |
| `text` | Texto | Opcional | Texto direto para debate (obrigatório se `file` não for enviado). |
| `file` | Arquivo | Opcional | Arquivo `.txt`, `.md`, `.pdf` ou `.log` com o conteúdo (obrigatório se `text` não for enviado). |
| `format` | Texto | `brief` | Formato: `deep_dive` (Análise detalhada), `brief` (Resumo), `critique` (Crítica) ou `debate` (Debate). |
| `length` | Texto | `default` | Duração: `short` (Curto), `default` (Padrão) ou `long` (Longo). |
| `language` | Texto | `pt` | Idioma do áudio (`pt` ou `pt-BR` para Português do Brasil). |
| `instructions`| Texto | Humor natural | Instruções de tom, foco e conduta para os apresentadores. |
| `webhook_url` | URL | Opcional | URL para notificação automática via `POST` quando o áudio estiver pronto (ex: n8n). |
| `cleanup_notebook` | Booleano | `true` | Exclui o caderno temporário do Google após o download para poupar cota. |
| `generate_video` | Booleano | `false` | Gera vídeo 16:9 (1080p) sincronizado ao áudio com transições e cartões dinâmicos. |
| `video_badge` | Texto | Opcional | Texto de identificação ou marca exibido no topo do cartão visual do vídeo. |

---

### Ciclo de Vida da Requisição

#### Passo 1: Solicitar a geração do podcast
Envie o conteúdo via JSON ou formulário `multipart/form-data`.

**Exemplo em cURL (JSON):**
```bash
curl -X POST "https://podcast.rodslater.com/api/v1/podcasts" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Novidades sobre Tecnologia",
    "text": "Conteúdo detalhado para ser debatido pelos apresentadores...",
    "language": "pt",
    "format": "brief",
    "length": "default",
    "generate_video": true,
    "video_badge": "BrasIRC Chatcast | #Brasil - 12/09/2026",
    "webhook_url": "https://seu-n8n.com/webhook/podcast-pronto"
  }'
```

**Exemplo em cURL (Arquivo .txt ou .pdf com vídeo):**
```bash
curl -X POST "https://podcast.rodslater.com/api/v1/podcasts" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -F "file=@relatorio.pdf" \
  -F "title=Podcast do Relatório" \
  -F "format=deep_dive" \
  -F "length=long" \
  -F "generate_video=true" \
  -F "video_badge=BrasIRC Chatcast | #Brasil - 12/09/2026"
```

**Resposta imediata (HTTP 202 Accepted):**
```json
{
  "job_id": "pod_a1b2c3d4e5f6",
  "title": "Novidades sobre Tecnologia",
  "status": "queued",
  "status_message": "Aguardando início do processamento.",
  "language": "pt",
  "format": "brief",
  "length": "default",
  "audio_file_name": null,
  "audio_size_bytes": null,
  "error_message": null,
  "status_url": "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6",
  "download_url": null,
  "created_at": "2026-09-11T14:30:00Z",
  "updated_at": "2026-09-11T14:30:00Z",
  "completed_at": null
}
```

---

#### Passo 2: Acompanhar o progresso
Consulte o status da tarefa a qualquer momento:

```bash
curl -X GET "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6" \
  -H "Authorization: Bearer SEU_TOKEN"
```

**Estados possíveis da tarefa (`status`):**
* `queued`: tarefa na fila aguardando processamento.
* `creating_notebook`: criando o caderno no Google NotebookLM.
* `uploading_source`: enviando o texto ou arquivo para a nuvem.
* `generating_audio`: áudio em geração pela IA do Google (duração típica: 3 a 8 minutos).
* `downloading_audio`: áudio finalizado pelo Google; baixando o `.m4a` para a VPS.
* `generating_video`: estruturando cenas com Gemini Flash, coletando fotos no Pexels e renderizando vídeo no FFmpeg.
* `completed`: processamento concluído com sucesso; áudio e vídeo disponíveis para download.
* `failed`: ocorreu uma falha (mensagem segura disponível em `error_message`).

**Resposta quando concluído:**
```json
{
  "job_id": "pod_a1b2c3d4e5f6",
  "title": "Novidades sobre Tecnologia",
  "status": "completed",
  "status_message": "Podcast e vídeo gerados com sucesso.",
  "audio_file_name": "pod_a1b2c3d4e5f6.m4a",
  "audio_size_bytes": 14285712,
  "generate_video": true,
  "video_file_name": "pod_a1b2c3d4e5f6.mp4",
  "video_size_bytes": 35841920,
  "download_url": "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6/download",
  "video_download_url": "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6/download-video"
}
```

---

#### Passo 3: Baixar o arquivo de áudio (.m4a)
Quando o status for `completed`, baixe o arquivo de áudio diretamente:

```bash
curl -X GET "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6/download" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -o "podcast_final.m4a"
```

---

#### Passo 3b: Baixar o arquivo de vídeo final (.mp4)
Se o vídeo foi solicitado (`generate_video=true`), baixe o `.mp4` diretamente:

```bash
curl -X GET "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6/download-video" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -o "podcast_video.mp4"
```

---

#### Passo 3c: Gerar vídeo para um podcast já existente
Você pode gerar o vídeo a qualquer momento a partir de um podcast concluído sem regerar o áudio, podendo inclusive definir ou sobrescrever o distintivo do cartão:

```bash
curl -X POST "https://podcast.rodslater.com/api/v1/podcasts/pod_a1b2c3d4e5f6/video?video_badge=BrasIRC%20Chatcast" \
  -H "Authorization: Bearer SEU_TOKEN"
```

---


#### Passo 4: Listar tarefas recentes
Para listar as últimas tarefas geradas pelo seu token:

```bash
curl -X GET "https://podcast.rodslater.com/api/v1/podcasts?limit=20" \
  -H "Authorization: Bearer SEU_TOKEN"
```

---

#### Passo 5: Verificação de Saúde
Endpoint público (sem necessidade de token) para monitoramento:

```bash
curl -X GET "https://podcast.rodslater.com/health"
```
Resposta:
```json
{"status":"ok","authenticated":true,"version":"0.1.0"}
```

---

## 5. Deploy em Produção

### 5.1. Produção Principal: VPS Hostinger via EasyPanel

A aplicação está hospedada em produção na VPS Hostinger com 4 vCPUs e 16 GB de RAM, garantindo renderização de vídeo Full HD em menos de 4 minutos.

#### 1. Criar aplicação no EasyPanel
* Acesse o EasyPanel e crie um novo serviço do tipo **App**.
* Na aba **Source / Git**, configure o repositório:
  * **Repository:** `Rodslater/api-notebooklm` (ou via deploy key SSH)
  * **Branch:** `main`
  * **Build Type:** `Dockerfile`

#### 2. Configurar Variáveis de Ambiente (Aba *Environment*)
```ini
PORT=8000
HOST=0.0.0.0

# Autenticação e tokens de acesso
API_TOKEN=seu_token_admin_mestre
API_TOKENS=brasirc:brasirc_BgIoZQR3-CbF58pOeJ1bAgV3RgG3ZjA861cIV3p19H0

# Diretórios internos de persistência
NOTEBOOKLM_AUTH_DIR=/app/data/auth
STORAGE_DIR=/app/storage

# Padrões do NotebookLM
DEFAULT_LANGUAGE=pt
DEFAULT_AUDIO_FORMAT=brief
DEFAULT_AUDIO_LENGTH=default
DEFAULT_INSTRUCTIONS=Apresente em português brasileiro natural, descontraído e bem-humorado. Os apresentadores devem demonstrar carisma, usar tiradas inteligentes, analogias divertidas e manter a conversa leve e cativante, resumindo os pontos essenciais com clareza.
GENERATION_TIMEOUT_SECONDS=1200
CLEANUP_NOTEBOOK=true

# Esteira de vídeo sincronizado (IA e Pexels)
GEMINI_API_KEY=sua_chave_gemini
GEMINI_MODEL=gemini-flash-latest
PEXELS_API_KEY=sua_chave_pexels
VIDEO_DIRECTOR_PROVIDER=gemini
VIDEO_FPS=30
```

#### 3. Volumes Persistentes (Aba *Mounts*)
Para preservar os áudios gerados e as credenciais de sessão do Google a cada novo deploy, configure os volumes:

| Tipo | Caminho no Container | Nome do Volume |
| :--- | :--- | :--- |
| Volume | `/app/data/auth` | `api-notebooklm-auth` |
| Volume | `/app/storage` | `api-notebooklm-storage` |

*Copie os arquivos de sessão `master_token.json` e `storage_state.json` para dentro do volume `/app/data/auth` para manter a autenticação ativa.*

#### 4. Domínio e Porta (Aba *Domains*)
* **Porta do Container:** `8000`
* **Domínio:** `podcast.rodslater.com` (o Traefik do EasyPanel emite o certificado SSL Let's Encrypt automaticamente).

---

### 5.2. Ambiente Alternativo: VPS Oracle (Docker Compose + Caddy)

Para rodar em servidores isolados sem EasyPanel:

#### 1. Estrutura de pastas
```bash
mkdir -p /home/ubuntu/apps/api-notebooklm/data/auth
mkdir -p /home/ubuntu/apps/api-notebooklm/storage
```

#### 2. Subir com Docker Compose
```bash
docker compose up -d --build
```

#### 3. Proxy Reverso com Caddy
No `Caddyfile`:
```caddy
podcast.rodslater.com {
    reverse_proxy api-notebooklm:8000

    request_body {
        max_size 50MB
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        -Server
    }
}
```
Recarregue o Caddy:
```bash
docker exec -w /etc/caddy caddy caddy reload
```
O Caddy solicitará o certificado SSL automaticamente e roteará as chamadas externas para o container da API.

---

## 6. Segurança, Isolamento e Tokens de API

Para proteger as credenciais do Google e permitir o uso por terceiros de forma isolada, a API implementa múltiplas camadas de segurança:

1. **Tokens Próprios da API (Multi-tenant):**
   * O token do Google (`master_token.json`) nunca é exposto aos usuários da API.
   * As chamadas externas exigem tokens Bearer independentes configurados nas variáveis `API_TOKEN` (administrador) e `API_TOKENS` (usuários adicionais).
   * Formato recomendado no `.env`: `API_TOKENS=cliente_a:token_secreto_a,cliente_b:token_secreto_b`.
   * Cada usuário só consegue listar, consultar o status e baixar os áudios gerados pelo seu próprio token. A tentativa de acessar tarefas de outro usuário retorna `404 Not Found`.

2. **Prevenção contra Path Traversal:**
   * Os nomes de arquivos enviados no upload são sanitizados via `Path(...).name` e recebem identificadores UUID únicos.
   * O endpoint de download valida obrigatoriamente se o caminho do arquivo está contido dentro da pasta restrita `storage/audios/`. Tentativas de apontar para arquivos de sistema ou pastas de autenticação são bloqueadas.

3. **Sanitização de Erros e Logs:**
   * Mensagens de erro retornadas pela API são higienizadas para remover tokens, cookies e parâmetros confidenciais.
   * Tracebacks detalhados ficam restritos aos logs internos do servidor e nunca são devolvidos no corpo das respostas HTTP.

