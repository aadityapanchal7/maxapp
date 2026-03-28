# Uploading prompts to AWS (S3)

These `.md` files are the **same keys** the app loads via `services/prompt_loader.py`.

## Object layout

Upload each file as:

`s3://<PROMPTS_S3_BUCKET>/<PROMPTS_S3_PREFIX>/<key>.md`

- **Bucket / prefix** come from your backend env (see `config.py`): `PROMPTS_S3_BUCKET`, `PROMPTS_S3_PREFIX` (if unset, prefix defaults to `prompts/prod`).
- **Key** = filename **without** `.md`, e.g. `max_chat_system.md` → key `max_chat_system`.

## Refresh this folder from code (recommended before upload)

From the `backend` directory:

```bash
python scripts/export_s3_prompts.py
```

That overwrites files here with the in-repo Python/string fallbacks so S3 matches what runs when the bucket is empty.

## Upload (AWS CLI example)

Replace `YOUR_BUCKET` and `YOUR_PREFIX` (e.g. `prompts/prod`):

```bash
aws s3 sync s3_prompts_upload s3://YOUR_BUCKET/YOUR_PREFIX --exclude "AWS_UPLOAD.md" --exclude "*.py"
```

Or upload a single prompt after editing:

```bash
aws s3 cp s3_prompts_upload/max_chat_system.md s3://YOUR_BUCKET/YOUR_PREFIX/max_chat_system.md
```

## After upload

- Prompts are **cached in process** after a successful S3 read. Restart API workers or call your deploy’s reload path if you add one.
- If `PROMPTS_S3_BUCKET` is empty, the API uses **code fallbacks only** and ignores these files.
