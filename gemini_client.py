"""
Módulo de análisis de imágenes usando chrome-lens-py.
Conecta directamente con el endpoint de Google Lens (como Chrome), sin API key ni límites.
"""

import asyncio
from chrome_lens_py import LensAPI


def _run_async(coro):
    """Ejecuta una coroutine asyncio desde código sincrónico."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# Mapa de nombres de idioma a códigos BCP-47
LANGUAGE_MAP = {
    "Afrikaans": "af", "Albanian": "sq", "Amharic": "am", "Arabic": "ar", "Armenian": "hy",
    "Azerbaijani": "az", "Basque": "eu", "Belarusian": "be", "Bengali": "bn", "Bosnian": "bs",
    "Bulgarian": "bg", "Catalan": "ca", "Cebuano": "ceb", "Chichewa": "ny", "Chinese (Simplified)": "zh-CN",
    "Chinese (Traditional)": "zh-TW", "Corsican": "co", "Croatian": "hr", "Czech": "cs", "Danish": "da",
    "Dutch": "nl", "English": "en", "Esperanto": "eo", "Estonian": "et", "Filipino": "tl",
    "Finnish": "fi", "French": "fr", "Frisian": "fy", "Galician": "gl", "Georgian": "ka",
    "German": "de", "Greek": "el", "Gujarati": "gu", "Haitian Creole": "ht", "Hausa": "ha",
    "Hawaiian": "haw", "Hebrew": "he", "Hindi": "hi", "Hmong": "hmn", "Hungarian": "hu",
    "Icelandic": "is", "Igbo": "ig", "Indonesian": "id", "Irish": "ga", "Italian": "it",
    "Japanese": "ja", "Javanese": "jw", "Kannada": "kn", "Kazakh": "kk", "Khmer": "km",
    "Korean": "ko", "Kurdish (Kurmanji)": "ku", "Kyrgyz": "ky", "Lao": "lo", "Latin": "la",
    "Latvian": "lv", "Lithuanian": "lt", "Luxembourgish": "lb", "Macedonian": "mk", "Malagasy": "mg",
    "Malay": "ms", "Malayalam": "ml", "Maltese": "mt", "Maori": "mi", "Marathi": "mr",
    "Mongolian": "mn", "Myanmar (Burmese)": "my", "Nepali": "ne", "Norwegian": "no", "Pashto": "ps",
    "Persian": "fa", "Polish": "pl", "Portuguese": "pt", "Punjabi": "pa", "Romanian": "ro",
    "Russian": "ru", "Samoan": "sm", "Scots Gaelic": "gd", "Serbian": "sr", "Sesotho": "st",
    "Shona": "sn", "Sindhi": "sd", "Sinhala": "si", "Slovak": "sk", "Slovenian": "sl",
    "Somali": "so", "Spanish": "es", "Sundanese": "su", "Swahili": "sw", "Swedish": "sv",
    "Tajik": "tg", "Tamil": "ta", "Telugu": "te", "Thai": "th", "Turkish": "tr",
    "Ukrainian": "uk", "Urdu": "ur", "Uzbek": "uz", "Vietnamese": "vi", "Welsh": "cy",
    "Xhosa": "xh", "Yiddish": "yi", "Yoruba": "yo", "Zulu": "zu"
}

def analyze_image(image_path, mode="translation", target_language="Spanish"):

    async def _do_request():
        async with LensAPI() as lens:
            if mode == "translation":
                lang_code = LANGUAGE_MAP.get(target_language, "es")
                result = await lens.process_image(
                    image_path,
                    target_translation_language=lang_code,
                    output_format="lines"
                )
                return result

            elif mode == "ocr":
                result = await lens.process_image(
                    image_path,
                    output_format="full_text"
                )
                return result

            else:  # lens mode
                result = await lens.process_image(
                    image_path,
                    output_format="lines"
                )
                return result

    try:
        result = _run_async(_do_request())

        if mode == "translation":
            # Convertir translation_render_data a formato JSON con bounding boxes
            import json
            render_data = result.get("translation_render_data", [])

            if not render_data:
                # Text is already in target language or no translation available
                # Fall back to line_blocks for positioning
                line_blocks = result.get("line_blocks", [])
                if not line_blocks:
                    return "[]"
                output = []
                for block in line_blocks:
                    text = block.get("text", "")
                    geo = block.get("geometry", {})
                    if not text or not geo:
                        continue
                    cx = geo.get("center_x", 0.5)
                    cy = geo.get("center_y", 0.5)
                    w = geo.get("width", 0.5)
                    h = geo.get("height", 0.05)
                    xmin = max(0, int((cx - w/2) * 1000))
                    ymin = max(0, int((cy - h/2) * 1000))
                    xmax = min(1000, int((cx + w/2) * 1000))
                    ymax = min(1000, int((cy + h/2) * 1000))
                    line_height = int(h * 1000)
                    output.append({"translated": text, "box": [ymin, xmin, ymax, xmax], "line_height": line_height})
                return json.dumps(output, ensure_ascii=False)

            output = []
            for block in render_data:
                translated_text = block.get("translation", "")
                if not translated_text:
                    continue
                lines = block.get("lines", [])
                if not lines:
                    continue

                # Merge all line geometries into one bounding box
                all_cx = [l["geometry"]["center_x"] for l in lines if "geometry" in l]
                all_cy = [l["geometry"]["center_y"] for l in lines if "geometry" in l]
                all_w  = [l["geometry"]["width"]    for l in lines if "geometry" in l]
                all_h  = [l["geometry"]["height"]   for l in lines if "geometry" in l]

                if not all_cx:
                    continue

                xmin_f = min(cx - w/2 for cx, w in zip(all_cx, all_w))
                xmax_f = max(cx + w/2 for cx, w in zip(all_cx, all_w))
                ymin_f = min(cy - h/2 for cy, h in zip(all_cy, all_h))
                ymax_f = max(cy + h/2 for cy, h in zip(all_cy, all_h))

                # Convert to 0-1000 scale and clamp
                xmin = max(0, int(xmin_f * 1000))
                ymin = max(0, int(ymin_f * 1000))
                xmax = min(1000, int(xmax_f * 1000))
                ymax = min(1000, int(ymax_f * 1000))
                
                avg_line_h = sum(all_h) / len(all_h)
                line_height = int(avg_line_h * 1000)

                output.append({
                    "translated": translated_text,
                    "box": [ymin, xmin, ymax, xmax],
                    "line_height": line_height
                })

            return json.dumps(output, ensure_ascii=False)

        elif mode == "ocr":
            text = result.get("ocr_text", "")
            if not text:
                return "No se detectó texto en la imagen."
            return text

        else:  # lens mode
            ocr = result.get("ocr_text", "")
            words = result.get("word_data", [])
            detected_lang = result.get("detected_language", "desconocido")
            obj_count = len(result.get("objects", []))

            summary = f"Idioma detectado: {detected_lang}\n"
            summary += f"Objetos identificados: {obj_count}\n"
            if ocr:
                summary += f"\nTexto encontrado:\n{ocr}"
            return summary

    except Exception as e:
        return f"Error connecting to Google Lens: {str(e)}"
