import gradio as gr
from github import Github
from groq import Groq
import time
import os
import zipfile
import base64

def call_groq_with_retry(client, model, messages, retries=5, delay=10):
    for i in range(retries):
        try:
            return client.chat.completions.create(model=model, messages=messages)
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                time.sleep(delay * (i + 1))
                continue
            raise e

def get_repo_data(repo, path="", depth=0, max_depth=1):
    structure = []
    file_contents = []
    priority_exts = {'py', 'js', 'ts', 'c', 'cpp', 'h', 'java', 'go', 'rs', 'php', 'md', 'yml', 'json'}
    try:
        contents = repo.get_contents(path)
        for content in contents:
            if content.type == "dir":
                structure.append(f"[DIR] {content.path}")
                if depth < max_depth:
                    time.sleep(0.1)
                    sub_struct, sub_cont = get_repo_data(repo, content.path, depth + 1, max_depth)
                    structure.extend(sub_struct)
                    file_contents.extend(sub_cont)
            else:
                structure.append(content.path)
                ext = content.path.split('.')[-1].lower()
                if ext in priority_exts and content.size < 30000:
                    try:
                        decoded_content = base64.b64decode(content.content).decode('utf-8')
                        file_contents.append(f"--- FILE: {content.path} ---\n{decoded_content[:1000]}\n")
                    except:
                        pass
    except:
        pass
    return structure, file_contents

def analyze_github(github_token_file, groq_key_file, target_user, progress=gr.Progress()):
    if github_token_file is None or groq_key_file is None or not target_user:
        return "⚠️ Vui lòng cung cấp đầy đủ 2 file Token/Key và nhập GitHub Username.", None

    try:
        github_token = open(github_token_file.name, "r").read().strip()
        groq_key = open(groq_key_file.name, "r").read().strip()

        g = Github(github_token)
        client = Groq(api_key=groq_key)
        
        user = g.get_user(target_user)
        all_repos = [r for r in user.get_repos() if not r.fork]
        total_repos = len(all_repos)
        
        report = f"# 🚀 Báo cáo GitHub: {target_user}\n\n"
        output_folder = f"analysis_{target_user}"
        os.makedirs(output_folder, exist_ok=True)

        for i, repo in enumerate(all_repos):
            progress((i + 1) / total_repos, desc=f"Đang xử lý {repo.name}")
            
            structure_list, contents_list = get_repo_data(repo)
            structure = "\n".join(structure_list)[:2000]
            snippet = "\n".join(contents_list)[:8000]

            try:
                response = call_groq_with_retry(
                    client,
                    "llama-3.3-70b-versatile",
                    [
                        {"role": "system", "content": "Bạn là chuyên gia phân tích mã nguồn. Phân tích logic và kiến trúc dựa trên code cung cấp bằng tiếng Việt."},
                        {"role": "user", "content": f"Repo: {repo.name}\nCấu trúc: {structure}\nCode: {snippet}"}
                    ]
                )
                ai_analysis = response.choices[0].message.content
            except Exception as e:
                ai_analysis = f"⚠️ Lỗi Rate Limit hoặc Hệ thống: {str(e)}"

            file_path = os.path.join(output_folder, f"{repo.name}_analysis.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"PROJECT: {repo.name}\nURL: {repo.html_url}\n{'-'*30}\n{ai_analysis}")
            
            report += f"### ✅ {repo.name}\n"
            time.sleep(3)

        zip_path = f"{output_folder}.zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, _, files in os.walk(output_folder):
                for file in files:
                    zipf.write(os.path.join(root, file), file)

        return report, zip_path

    except Exception as e:
        return f"❌ Lỗi: {str(e)}", None

with gr.Blocks(title="GitHub AI Analyzer (Groq)") as demo:
    gr.Markdown("# ⚡ GitHub Repo AI Content Analyzer")
    gr.Markdown("Phân tích chuyên sâu nội dung code với cơ chế tự động thử lại khi gặp Rate Limit.")
    
    with gr.Column():
        github_in = gr.File(label="1. Upload github_token.txt")
        groq_in = gr.File(label="2. Upload groq_api_key.txt")
        user_in = gr.Textbox(label="3. Nhập GitHub Username", placeholder="ví dụ: trinhphucuong")
        btn = gr.Button("🚀 Bắt đầu phân tích", variant="primary")
        
        output_text = gr.Markdown()
        output_file = gr.File(label="📥 Tải về bản nén (.zip)")

    btn.click(fn=analyze_github, inputs=[github_in, groq_in, user_in], outputs=[output_text, output_file])

if __name__ == "__main__":
    demo.launch()