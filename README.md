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

## 4. Endpoints da API

### A. Criar tarefa de podcast
* **Rota:** `POST /api/v1/podcasts`
* **Autenticação:** `Authorization: Bearer <API_TOKEN>`
* **Formatos aceitos:** `multipart/form-data` ou `application/json`

#### Exemplo 1: Envio de arquivo `.txt` via cURL
```bash
curl -X POST "http://localhost:8000/api/v1/podcasts" \
  -H "Authorization: Bearer dev_token_notebooklm_2026" \
  -F "file=@noticia.txt" \
  -F "title=Resumo Matinal" \
  -F "format=brief"
```

#### Exemplo 2: Envio de texto via JSON
```bash
curl -X POST "http://localhost:8000/api/v1/podcasts" \
  -H "Authorization: Bearer dev_token_notebooklm_2026" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Podcast Semanal",
    "text": "O tema de hoje abrange as novidades tecnologicas...",
    "format": "brief",
    "length": "default",
    "language": "pt",
    "webhook_url": "https://seu-n8n.com/webhook/podcast-pronto"
  }'
```

#### Resposta (HTTP 202 Accepted):
```json
{
  "job_id": "pod_a1b2c3d4e5f6",
  "title": "Podcast Semanal",
  "status": "queued",
  "status_message": "Aguardando início do processamento.",
  "language": "pt",
  "format": "brief",
  "length": "default",
  "audio_file_name": null,
  "audio_size_bytes": null,
  "error_message": null,
  "status_url": "/api/v1/podcasts/pod_a1b2c3d4e5f6",
  "download_url": null,
  "created_at": "2026-09-11T14:30:00Z",
  "updated_at": "2026-09-11T14:30:00Z",
  "completed_at": null
}
```

---

### B. Consultar status da tarefa
* **Rota:** `GET /api/v1/podcasts/{job_id}`
* **Autenticação:** `Authorization: Bearer <API_TOKEN>`

#### Resposta quando concluído:
```json
{
  "job_id": "pod_a1b2c3d4e5f6",
  "title": "Podcast Semanal",
  "status": "completed",
  "status_message": "Podcast gerado e disponível para download.",
  "audio_file_name": "pod_a1b2c3d4e5f6.m4a",
  "audio_size_bytes": 14285712,
  "download_url": "/api/v1/podcasts/pod_a1b2c3d4e5f6/download"
}
```

---

### C. Baixar áudio do podcast
* **Rota:** `GET /api/v1/podcasts/{job_id}/download`
* **Autenticação:** `Authorization: Bearer <API_TOKEN>`
* Retorna o arquivo binário `audio/mp4` (`.m4a`) pronto para reprodução.

---

### D. Verificação de Saúde
* **Rota:** `GET /health`
* Não exige token. Retorna o status operacional do servidor e se há credenciais configuradas.

---

## 5. Deploy na VPS Oracle (147.15.18.148)

A VPS já conta com Docker e o Caddy rodando na rede Docker compartilhada chamada `proxy`.

### 1. Criar pasta da aplicação na VPS
Na VPS, crie a pasta em `/home/ubuntu/apps/api-notebooklm`:
```bash
mkdir -p /home/ubuntu/apps/api-notebooklm/data/auth
mkdir -p /home/ubuntu/apps/api-notebooklm/storage
```

### 2. Copiar os arquivos
Copie o código-fonte, o `.env` e o arquivo `master_token.json` para a pasta na VPS.

### 3. Subir o container Docker
Dentro da pasta `/home/ubuntu/apps/api-notebooklm`:
```bash
docker compose up -d --build
```

### 4. Configurar no Caddyfile da VPS
Edite o arquivo `/home/ubuntu/apps/caddy/Caddyfile` e adicione o bloco para o subdomínio desejado (exemplo: `podcast.rodslater.com`):

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
