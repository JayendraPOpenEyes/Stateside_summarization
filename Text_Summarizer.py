import os
import re
import requests
import io
import logging
import json
from bs4 import BeautifulSoup
from PIL import Image
from pdf2image import convert_from_bytes
from dotenv import load_dotenv
import pdfkit
import tiktoken
from openai import OpenAI
import pytesseract  # For OCR

# Load environment variables from .env file
# load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Base directory to save all data
SAVE_DIR = "saved_data"
os.makedirs(SAVE_DIR, exist_ok=True)

class TextProcessor:
    def __init__(self, model="gpt-4o-mini"):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OpenAI API key is missing. Ensure the OPENAI_API_KEY is set in the .env file.")
        self.openai_client = OpenAI(api_key=self.openai_api_key)
        self.model = model

    def get_save_directory(self, base_name):
        folder_path = os.path.join(SAVE_DIR, base_name)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path

    def get_base_name_from_link(self, link):
        parts = link.split('/')
        meaningful_parts = [part for part in parts[-4:] if part and part.lower() not in ['pdf', 'html', 'htm']]
        base_name = '_'.join(meaningful_parts) or '_'.join(parts)
        base_name = re.sub(r"\.(htm|html|pdf)$", "", base_name, flags=re.IGNORECASE)
        base_name = re.sub(r"[^\w\-_\. ]", "_", base_name)
        if len(base_name) > 50:
            base_name = base_name[:50]
        return base_name or "default_name"

    def is_google_cache_link(self, link):
        return "webcache.googleusercontent.com" in link

    def is_blank_text(self, text):
        clean_text = re.sub(r"\s+", "", text).strip()
        return len(clean_text) < 100

    def process_image_with_tesseract(self, image_path):
        try:
            return pytesseract.image_to_string(Image.open(image_path))
        except Exception as e:
            logging.error(f"Error processing image with Tesseract: {str(e)}")
            return ""

    def extract_text_from_pdf(self, pdf_content, link):
        base_name = self.get_base_name_from_link(link)
        folder = self.get_save_directory(base_name)
        images = convert_from_bytes(pdf_content.read())
        combined_text = ""
        for i, img in enumerate(images):
            img_filename = f"{base_name}_page_{i+1}.png"
            img_path = os.path.join(folder, img_filename)
            img.save(img_path, 'PNG')
            logging.info(f"Saved image: {img_path}")
            combined_text += self.process_image_with_tesseract(img_path) + "\n"
        return combined_text

    def extract_text_from_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup(['script', 'style']):
            tag.decompose()
        return soup.get_text(separator=' ').strip()

    def extract_text_from_url(self, url):
        try:
            if self.is_google_cache_link(url):
                return {"text": "", "content_type": None, "error": "google_cache"}
            response = requests.get(url)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower()
            base_name = self.get_base_name_from_link(url)
            folder = self.get_save_directory(base_name)
            if url.lower().endswith('.pdf') or 'application/pdf' in content_type:
                pdf_path = os.path.join(folder, f"{base_name}.pdf")
                with open(pdf_path, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Saved PDF: {pdf_path}")
                text = self.extract_text_from_pdf(io.BytesIO(response.content), url)
                if self.is_blank_text(text):
                    return {"text": "", "content_type": "pdf", "error": "blank_pdf"}
                return {"text": text, "content_type": "pdf", "error": None}
            elif url.lower().endswith(('.htm', '.html')) or 'text/html' in content_type:
                html_path = os.path.join(folder, f"{base_name}.html")
                with open(html_path, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Saved HTML: {html_path}")
                text = self.extract_text_from_html(response.content)
                return {"text": text, "content_type": "html", "error": None}
            else:
                return {"text": "", "content_type": None, "error": "unsupported_type"}
        except Exception as e:
            logging.error(f"Error fetching URL {url}: {str(e)}")
            return {"text": "", "content_type": None, "error": str(e)}

    def process_uploaded_pdf(self, pdf_file, base_name="uploaded_pdf"):
        try:
            folder = self.get_save_directory(base_name)
            pdf_path = os.path.join(folder, f"{base_name}.pdf")
            pdf_bytes = pdf_file.read()
            if not pdf_bytes:
                return {"text": "", "content_type": "pdf", "error": "Empty PDF file"}
            with open(pdf_path, 'wb') as f:
                f.write(pdf_bytes)
            logging.info(f"Saved uploaded PDF: {pdf_path}")
            pdf_io = io.BytesIO(pdf_bytes)
            images = convert_from_bytes(pdf_io.read())
            logging.info(f"Converted {len(images)} page(s) to images.")
            combined_text = ""
            for i, img in enumerate(images):
                img_filename = f"{base_name}_page_{i+1}.png"
                img_path = os.path.join(folder, img_filename)
                img.save(img_path, 'PNG')
                logging.info(f"Saved image: {img_path}")
                combined_text += self.process_image_with_tesseract(img_path) + "\n"
            if self.is_blank_text(combined_text):
                return {"text": "", "content_type": "pdf", "error": "blank_pdf"}
            return {"text": combined_text, "content_type": "pdf", "error": None}
        except Exception as e:
            logging.error(f"Error processing uploaded PDF: {str(e)}")
            return {"text": "", "content_type": None, "error": str(e)}

    def process_uploaded_html(self, html_file, base_name="uploaded_html"):
        try:
            folder = self.get_save_directory(base_name)
            html_path = os.path.join(folder, f"{base_name}.html")
            html_bytes = html_file.read()
            if not html_bytes:
                return {"text": "", "content_type": "html", "error": "Empty HTML file"}
            with open(html_path, 'wb') as f:
                f.write(html_bytes)
            logging.info(f"Saved uploaded HTML: {html_path}")
            text = self.extract_text_from_html(html_bytes)
            return {"text": text, "content_type": "html", "error": None}
        except Exception as e:
            logging.error(f"Error processing uploaded HTML: {str(e)}")
            return {"text": "", "content_type": None, "error": str(e)}

    def preprocess_text(self, text):
        text = re.sub(r"[\r\n]{2,}", "\n", text)
        text = re.sub(r"[^\x00-\x7F]+", " ", text)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()

    def generate_html_structure(self, text):
        paragraphs = text.split('\n')
        html = ""
        for para in paragraphs:
            if len(para.split()) > 10:
                html += f"<p>{para.strip()}</p>\n"
            else:
                html += f"<h1>{para.strip()}</h1>\n"
        return html

    def generate_json_with_prompt(self, html, base_name):
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ').strip()
        # Updated prompt: instruct the model not to summarize or omit details.
        prompt = (
            "Convert the following text into a structured JSON format with keys 'h1' and 'p'.\n"
            "Do not summarize or omit any details; preserve the entire text structure.\n"
            "Return only the JSON enclosed in triple backticks, with no extra commentary.\n\n" + text
        )
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,  # Increased to allow more output
            )
            json_output = response.choices[0].message.content.strip()
            json_output = re.sub(r"^```(?:json)?\s*", "", json_output)
            json_output = re.sub(r"\s*```$", "", json_output)
            try:
                json_data = json.loads(json_output)
            except json.JSONDecodeError:
                json_match = re.search(r'(\{.*\})', json_output, re.DOTALL)
                if json_match:
                    try:
                        json_data = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        logging.error("Invalid JSON from OpenAI after regex extraction.")
                        return {}
                else:
                    logging.error("OpenAI response is not valid JSON format.")
                    return {}
            base_folder = self.get_save_directory(base_name)
            json_path = os.path.join(base_folder, f"{base_name}.json")
            with open(json_path, 'w') as json_file:
                json.dump(json_data, json_file, indent=4)
            logging.info(f"Saved JSON: {json_path}")
            return json_data
        except Exception as e:
            logging.error(f"Error generating JSON with OpenAI: {str(e)}")
            return {}

    def truncate_text(self, text, max_tokens=3000):
        encoding = tiktoken.encoding_for_model(self.model)
        tokens = encoding.encode(text)
        if len(tokens) > max_tokens:
            tokens = tokens[:max_tokens]
        return encoding.decode(tokens)

    def generate_summaries_with_chatgpt(self, combined_text):
        combined_text = self.truncate_text(combined_text, max_tokens=4000)
        prompt = f"""
Generate the following summaries for the text below. Please adhere to these instructions:

For Abstractive Summary:
- Provide a concise summary in one short paragraph (maximum 8 sentences).

For Extractive Summary:
- Provide a summary capturing the main ideas in at least 2 paragraphs if possible.

For Highlights & Analysis:
- Provide 15 to 20 bullet points grouped under 4 meaningful headings.
- Each heading should be followed by bullet points of key details.

Use the following markers exactly for each section:

Abstractive Summary:
[Abstractive]

Extractive Summary:
[Extractive]

Highlights & Analysis:
[Highlights]

Only output the text within these markers without any additional commentary.

Text:
{combined_text}
"""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=1500,
            )
            summaries = response.choices[0].message.content
            abstractive_match = re.search(r"\[Abstractive\](.*?)\[Extractive\]", summaries, re.DOTALL)
            extractive_match = re.search(r"\[Extractive\](.*?)\[Highlights\]", summaries, re.DOTALL)
            highlights_match = re.search(r"\[Highlights\](.*)", summaries, re.DOTALL)
            return {
                "extractive": extractive_match.group(1).strip() if extractive_match else "Extractive summary not found.",
                "abstractive": abstractive_match.group(1).strip() if abstractive_match else "Abstractive summary not found.",
                "highlights": highlights_match.group(1).strip() if highlights_match else "Highlights not found."
            }
        except Exception as e:
            logging.error(f"Error generating summaries: {str(e)}")
            return {
                "extractive": "Error generating extractive summary.",
                "abstractive": "Error generating abstractive summary.",
                "highlights": "Error generating highlights."
            }

    def process_full_text_to_json(self, text, base_name):
        html = self.generate_html_structure(text)
        return self.generate_json_with_prompt(html, base_name)

    def process_raw_text(self, text, base_name="raw_text"):
        clean_text = self.preprocess_text(text)
        summaries = self.generate_summaries_with_chatgpt(clean_text)
        self.process_full_text_to_json(clean_text, base_name)
        return {
            "model": self.model,
            "extractive": summaries["extractive"],
            "abstractive": summaries["abstractive"],
            "highlights": summaries["highlights"]
        }

def process_input(input_data, model="gpt-4o-mini"):
    try:
        processor = TextProcessor(model=model)
        if hasattr(input_data, "read") and not isinstance(input_data, str):
            file_identifier = input_data.name if hasattr(input_data, "name") else "uploaded_file"
            logging.info(f"Processing uploaded file: {file_identifier}")
            _, ext = os.path.splitext(file_identifier)
            ext = ext.lower()
            if ext in [".htm", ".html"]:
                result = processor.process_uploaded_html(input_data, base_name=file_identifier[-7:] if len(file_identifier) >= 7 else file_identifier)
            elif ext == ".pdf":
                result = processor.process_uploaded_pdf(input_data, base_name=file_identifier[-7:] if len(file_identifier) >= 7 else file_identifier)
            else:
                result = {"text": input_data.read(), "content_type": "raw", "error": None}
            if result["error"]:
                return {"error": result["error"], "model": model}
            clean_text = processor.preprocess_text(result["text"])
            base_name = file_identifier[-7:] if len(file_identifier) >= 7 else file_identifier
        elif isinstance(input_data, str) and input_data.startswith(("http://", "https://")):
            result = processor.extract_text_from_url(input_data)
            if result["error"]:
                return {"error": result["error"], "model": model}
            clean_text = processor.preprocess_text(result["text"])
            base_name = processor.get_base_name_from_link(input_data)
        elif isinstance(input_data, str):
            clean_text = processor.preprocess_text(input_data)
            base_name = "raw_text"
        else:
            return {"error": "Invalid input type. Expected URL, raw text, or an uploaded file.", "model": model}
        summaries = processor.generate_summaries_with_chatgpt(clean_text)
        processor.process_full_text_to_json(clean_text, base_name)
        return {
            "model": model,
            "extractive": summaries["extractive"],
            "abstractive": summaries["abstractive"],
            "highlights": summaries["highlights"]
        }
    except Exception as e:
        logging.error(f"Error processing input: {str(e)}")
        return {"error": f"An error occurred: {str(e)}", "model": model}
