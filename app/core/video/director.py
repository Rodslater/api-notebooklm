import asyncio
import base64
import json
import logging
import subprocess
from pathlib import Path
import httpx

from app.config import settings
from app.core.video.models import VideoScene
from app.core.video.renderer import get_ffmpeg_path

logger = logging.getLogger(__name__)


async def direct_video_scenes(
    audio_path: Path,
    audio_duration_sec: float,
    podcast_title: str,
) -> list[VideoScene]:
    """Analisa o áudio e gera a divisão temporal com tópicos e termos de busca."""
    if settings.gemini_api_key:
        try:
            return await _direct_with_gemini(audio_path, audio_duration_sec, podcast_title)
        except Exception as exc:
            logger.warning("Falha ao analisar áudio com Gemini Flash: %s. Aplicando divisão com temas variados.", exc)

    if settings.openai_api_key and settings.video_director_provider == "openai":
        try:
            return await _direct_with_openai(audio_path, audio_duration_sec, podcast_title)
        except Exception as exc:
            logger.warning("Falha ao analisar áudio com OpenAI: %s. Aplicando divisão com temas variados.", exc)

    return _generate_fallback_scenes(audio_duration_sec, podcast_title)


def _create_compact_audio_for_gemini(audio_path: Path) -> Path:
    """Gera uma cópia ultraleve mono em 24k para análise rápida pela IA sem estourar limites."""
    compact_path = audio_path.parent / f"gemini_compact_{audio_path.stem}.m4a"
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "24k",
        str(compact_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return compact_path


async def _direct_with_gemini(
    audio_path: Path,
    audio_duration_sec: float,
    podcast_title: str,
) -> list[VideoScene]:
    """Chama a API do Gemini Flash com áudio compactado para estruturar cenas e termos únicos de busca."""
    compact_audio = _create_compact_audio_for_gemini(audio_path)

    try:
        file_bytes = compact_audio.read_bytes()
        b64_audio = base64.b64encode(file_bytes).decode("utf-8")

        prompt = (
            f"Você é um diretor de vídeo para podcasts. Analise o áudio fornecido intitulado '{podcast_title}' "
            f"com duração de {audio_duration_sec:.1f} segundos. "
            "Divida a linha do tempo em blocos contínuos de aproximadamente 15 a 20 segundos cada. "
            "Para cada bloco, forneça: "
            "1. start_sec (segundo inicial) "
            "2. end_sec (segundo final) "
            "3. topic (título conciso do tema tratado no trecho em português do Brasil, máximo 6 palavras, com acentos corretos) "
            "4. search_query (expressão de busca em inglês com 2 a 4 palavras para encontrar fotos no Pexels; "
            "use termos visuais variados e específicos para o assunto daquele trecho exato). "
            "Retorne exclusivamente uma lista JSON válida de objetos contendo: start_sec, end_sec, topic, search_query. "
            f"Os blocos devem cobrir continuamente de 0.0 até {audio_duration_sec:.1f} segundos sem lacunas."
        )

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
            f"?key={settings.gemini_api_key}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "audio/mp4",
                                "data": b64_audio,
                            }
                        },
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        }

        # Tentativa com retentativas para evitar falhas transitórias
        last_error = None
        for attempt in range(1, 4):
            try:
                timeout_config = httpx.Timeout(180.0, connect=30.0)
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    break
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                logger.warning("Tentativa %d de chamada ao Gemini Flash falhou: %r", attempt, exc)
                if attempt < 3:
                    await asyncio.sleep(attempt * 2.0)
        else:
            raise last_error or RuntimeError("Falha ao comunicar com Gemini após 3 tentativas.")

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)

        scenes: list[VideoScene] = []
        current_time = 0.0

        for idx, item in enumerate(parsed):
            start = float(item.get("start_sec", current_time))
            end = float(item.get("end_sec", start + 18.0))
            topic = str(item.get("topic", podcast_title)).strip()
            query = str(item.get("search_query", "business technology podcast")).strip()

            if end <= start:
                end = start + 18.0

            scenes.append(
                VideoScene(
                    index=idx,
                    start_sec=round(start, 2),
                    end_sec=round(end, 2),
                    topic=topic,
                    search_query=query,
                )
            )
            current_time = end

        if scenes:
            scenes[-1].end_sec = max(scenes[-1].end_sec, audio_duration_sec)

        return scenes

    finally:
        compact_audio.unlink(missing_ok=True)


async def _direct_with_openai(
    audio_path: Path,
    audio_duration_sec: float,
    podcast_title: str,
) -> list[VideoScene]:
    """Alternativa usando Whisper para transcrição e GPT-4o-mini para roteiro visual."""
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    compact_audio = _create_compact_audio_for_gemini(audio_path)

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            with open(compact_audio, "rb") as f:
                files = {"file": (compact_audio.name, f, "audio/mp4")}
                data = {"model": "whisper-1", "response_format": "verbose_json"}
                tr_resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                )
                tr_resp.raise_for_status()
                transcript_data = tr_resp.json()

            full_text = transcript_data.get("text", "")
            prompt = (
                f"Analise a transcrição do podcast '{podcast_title}' com duração de {audio_duration_sec:.1f}s. "
                "Divida em blocos de 15 a 20s. Para cada bloco forneça start_sec, end_sec, topic (português) "
                "e search_query (inglês para busca de foto no Pexels com termos variados para cada trecho). "
                f"Retorne JSON: [{{\"start_sec\": 0.0, \"end_sec\": 18.0, \"topic\": \"...\", \"search_query\": \"...\"}}].\n\n"
                f"Texto: {full_text}"
            )

            chat_resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            chat_resp.raise_for_status()
            chat_data = chat_resp.json()
            content = chat_data["choices"][0]["message"]["content"]
            raw_list = json.loads(content)
            if isinstance(raw_list, dict):
                raw_list = raw_list.get("scenes", raw_list.get("segments", list(raw_list.values())[0]))

        scenes = []
        for idx, item in enumerate(raw_list):
            scenes.append(
                VideoScene(
                    index=idx,
                    start_sec=float(item["start_sec"]),
                    end_sec=float(item["end_sec"]),
                    topic=str(item["topic"]),
                    search_query=str(item["search_query"]),
                )
            )
        return scenes
    finally:
        compact_audio.unlink(missing_ok=True)


def _generate_fallback_scenes(
    audio_duration_sec: float,
    podcast_title: str,
) -> list[VideoScene]:
    """Cria divisão de cenas com tópicos e termos visuais rotativos quando não houver IA disponível."""
    step = 18.0
    scenes: list[VideoScene] = []
    current = 0.0
    idx = 0

    clean_title = podcast_title.strip() or "Podcast em Áudio"

    # Termos temáticos variados para que mesmo o fallback nunca repita a mesma imagem
    fallback_themes = [
        ("Apresentação e início do debate", "podcast microphone studio"),
        ("Origem do tema e discussões", "retro computer internet chat"),
        ("Ponto central da conversa", "technology data center server"),
        ("Análise detalhada dos fatos", "software developer typing terminal"),
        ("Momentos marcantes do dia", "neon nightlife city lights"),
        ("Reflexão dos apresentadores", "people laughing coffee talk"),
        ("Perspectivas e conclusões", "futuristic digital technology"),
        ("Encerramento do episódio", "audio sound mixer studio"),
    ]

    while current < audio_duration_sec:
        end = min(current + step, audio_duration_sec)
        theme_idx = idx % len(fallback_themes)
        topic_suffix, query = fallback_themes[theme_idx]

        topic = clean_title if idx == 0 else f"{clean_title}: {topic_suffix}"
        scenes.append(
            VideoScene(
                index=idx,
                start_sec=round(current, 2),
                end_sec=round(end, 2),
                topic=topic,
                search_query=query,
            )
        )
        current = end
        idx += 1

    return scenes
