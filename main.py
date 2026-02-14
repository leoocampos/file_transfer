from flask import Flask, jsonify
from googleapiclient.discovery import build
from google.cloud import storage
from google.auth import default
import tempfile
import os

# CONFIGURAÇÕES
# =====================
FOLDER_ORIGEM = "12hs-FDKNkljlRuN8jslq9yaTHRUca_b4"
FOLDER_DESTINO = "1RoCp78rwBczqxSxV4z1cO70nGFjIFkod"
BUCKET_NAME = "sample-track-files"

app = Flask(__name__)

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
# FUNÇÕES DE NEGÓCIO
# =====================
def listar_arquivos_pasta(drive_service, folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query).execute()
    return results.get("files", [])


def copiar_para_bucket(drive_service, bucket, file_id, file_name):
    temp_name = os.path.join(tempfile.gettempdir(), file_name)

    request = drive_service.files().get_media(fileId=file_id)
    with open(temp_name, "wb") as f:
        f.write(request.execute())

    bucket.blob(file_name).upload_from_filename(temp_name)
    os.remove(temp_name)


def mover_arquivo(drive_service, file_id):
    drive_service.files().update(
        fileId=file_id,
        addParents=FOLDER_DESTINO,
        removeParents=FOLDER_ORIGEM
    ).execute()


def processar_arquivos():
    drive_service, bucket = get_clients()
    arquivos = listar_arquivos_pasta(drive_service, FOLDER_ORIGEM)

    if not arquivos:
        return {"status": "ok", "message": "Nenhum arquivo encontrado."}

    for arq in arquivos:
        copiar_para_bucket(drive_service, bucket, arq["id"], arq["name"])
        mover_arquivo(drive_service, arq["id"])

    return {
        "status": "success",
        "processed_files": len(arquivos)
    }


# =====================
# ENDPOINT CLOUD RUN
# =====================
@app.post("/functions/file-transfer")
def file_transfer():
    resultado = processar_arquivos()
    return jsonify(resultado), 200


# =====================
# ENTRYPOINT LOCAL
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)