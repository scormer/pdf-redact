import streamlit as st
import fitz
from  openai import OpenAI
import os
from dotenv import load_dotenv
import json
import re
from io import BytesIO

load_dotenv()

# openai.api_key = os.getenv("OPENAI_API_KEY")
key= os.getenv("OPENAI_API_KEY")
client=OpenAI(api_key=key)


def extract_entities_openai(page_text, page_num, system_prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": "The page content is:\n\n\n"+page_text},
            ],
        )
        json_output = response.choices[0].message.content
        # print (json_output)
        data = json.loads(json_output)
        return {page_num: data}

    except Exception as e:
        print(f"Error extracting entities from page {page_num}: {e}")
        return {page_num: {}}


def create_redact_set(entities_per_page):
    redact_set = set()
    for page_num, entities in entities_per_page.items():
        if entities:
            for _, entity_info in entities.items():
                for field, value in entity_info.items():
                    if value:
                       # Split the value into words and add to redact_set
                        for word in value.split():
                             redact_set.add(word)
    return redact_set

def save_list_to_file(data_list, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        for item in data_list:
            f.write(str(item) + '\n')
            
def save_set_to_file(data_set, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        for item in data_set:
            f.write(str(item) + '\n')

def trim_punctuation(text):
    return re.sub(r'[\.,!?;:]+$', '', text)


def redact_pdf(pdf_file, system_prompt):
    doc = fitz.open(pdf_file)
    for page_num, page in enumerate(doc, 1):
        word_list = []
        page_text = page.get_text()
        words = page.get_text("words")
        for word in words:
            x0, y0, x1, y1, text, block_no, line_no, word_no = word
            trimmed_text = trim_punctuation(text)
            word_list.append({"page": page_num, "text": trimmed_text, "position": (x0, y0, x1, y1)})
        
        entities_per_page = extract_entities_openai(page_text, page_num, system_prompt)
        redact_set = create_redact_set(entities_per_page)

        save_list_to_file(word_list, f'word_list_page_{page_num}.txt')
        save_set_to_file(redact_set, f'redact_set_page_{page_num}.txt')

        for word_info in word_list:
          if word_info["text"].lower() in [item.lower() for item in redact_set]:
             page.draw_rect(fitz.Rect(*word_info["position"]), color=(0, 0, 0), fill=(0, 0, 0)) # Black box
    
    output_pdf = BytesIO()
    doc.save(output_pdf)
    output_pdf.seek(0)
    return output_pdf


def build_system_prompt(redact_options):
    prompt_parts = []
    if "Name" in redact_options:
        prompt_parts.append("names")
    if "Email" in redact_options:
        prompt_parts.append("emails")
    if "Address" in redact_options:
        prompt_parts.append("addresses")
    if "Phone Number" in redact_options:
        prompt_parts.append("phone numbers")

    if not prompt_parts:
        return ""
    
    prompt_string = "You are an expert in identifying sensitive information. Extract all " + ", ".join(prompt_parts) + " from the following text. Output the answer in JSON format, The Key should be the ordinal number of the information found, for example '1','2','3' etc. If not found, the corresponding values should be an empty string. The output should look like: {\"1\":{\"Name\": \"\",\"Phone\": \"\",\"Email\": \"\",\"Address\": \"\"}, \"2\":{\"Name\": \"\",\"Phone\": \"\",\"Email\": \"\",\"Address\": \"\"}}. Only return the JSON, nothing else."
    return prompt_string


def main():
    st.title("PDF Redaction Tool")

    st.header("1. Select Redaction Options")
    redact_options = st.multiselect(
        "What information do you want to redact?",
        ["Name", "Email", "Address", "Phone Number"],
        default=["Name", "Email", "Phone Number"]
    )

    system_prompt = build_system_prompt(redact_options)

    if not system_prompt:
        st.warning("Please select at least one redaction option.")
        return

    st.header("2. Upload PDF File")
    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    if uploaded_file is not None:
        if st.button("Redact PDF"):
            with st.spinner("Redacting PDF..."):
                redacted_pdf = redact_pdf(uploaded_file, system_prompt)
                
            st.header("3. Download Redacted PDF")
            st.download_button(
                label="Download Redacted PDF",
                data=redacted_pdf,
                file_name=f"{os.path.splitext(uploaded_file.name)[0]}_redacted.pdf",
                mime="application/pdf",
            )


if __name__ == "__main__":
    main()