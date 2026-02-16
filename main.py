from flask import Flask, jsonify
from googleapiclient.discovery import build
from google.cloud import storage
from google.auth import default
from googleapiclient.errors import HttpError
import tempfile
import os
import logging

# =====================
# CONFIGURAÇÕES
# =====================
FOLDER_ORIGEM = "12hs-FDKNkljlRuN8jslq9yaTHRUca_b4"
BUCKET_NAME = "sample-track-files"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# =====================
# CLIENTES GCP
# =====================
def get_clients():
    creds, _ = default()
    drive_service = build("drive", "v3", credentials=creds)
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    return drive_service, bucket


# =====================
# FUNÇÕES
# =====================
def listar_arquivos_pasta(drive_service, folder_id):
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query).execute()
        return results.get("files", [])
    except HttpError as e:
        logging.error(f"Erro ao listar arquivos: {e}")
        raise


def mover_para_bucket(drive_service, bucket, file_id, file_name):
    temp_path = os.path.join(tempfile.gettempdir(), file_name)

    try:
        # 1️⃣ Baixa do Drive
        request = drive_service.files().get_media(fileId=file_id)
        with open(temp_path, "wb") as f:
            f.write(request.execute())

        # 2️⃣ Upload para o Cloud Storage
        bucket.blob(file_name).upload_from_filename(temp_path)

        # 3️⃣ Remove do Drive (MOVE real)
        drive_service.files().delete(fileId=file_id).execute()

        logging.info(f"Arquivo movido com sucesso: {file_name}")

    except Exception as e:
        logging.error(f"Erro ao mover arquivo {file_name}: {e}")
        raise

    finally:
        # Garante limpeza do arquivo temporário
        if os.path.exists(temp_path):
            os.remove(temp_path)


def processar_arquivos():
    try:
        drive_service, bucket = get_clients()
        arquivos = listar_arquivos_pasta(drive_service, FOLDER_ORIGEM)

        # ✅ Caso não tenha arquivos
        if not arquivos:
            logging.info("Nenhum arquivo encontrado na pasta.")
            return {
                "status": "ok",
                "message": "Nenhum arquivo encontrado."
            }, 200

        arquivos_processados = 0

        for arq in arquivos:
            try:
                mover_para_bucket(
                    drive_service,
                    bucket,
                    arq["id"],
                    arq["name"]
                )
                arquivos_processados += 1
            except Exception as erro_individual:
                logging.error(f"Falha ao processar {arq['name']}: {erro_individual}")

        return {
            "status": "success",
            "processed_files": arquivos_processados
        }, 200

    except Exception as e:
        logging.error(f"Erro geral no processamento: {e}")
        return {
            "status": "error",
            "message": "Erro ao processar arquivos.",
            "details": str(e)
        }, 500


# =====================
# ENDPOINT CLOUD RUN
# =====================
@app.post("/file_transfer")
def file_transfer():
    resultado, status_code = processar_arquivos()
    return jsonify(resultado), status_code


# =====================
# ENTRYPOINT LOCAL
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
