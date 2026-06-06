# w.LiGHTER Next.js Frontend

Reference-image oriented UI replacement for the previous Streamlit screens.

## Run

Terminal 1, Python API:

```powershell
$env:WLIGHTER_MOCK_MODE='true'
python ..\api_server.py
```

Terminal 2, Next.js:

```powershell
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## API base

The frontend calls:

```text
http://127.0.0.1:8000
```

Override with:

```powershell
$env:NEXT_PUBLIC_WLIGHTER_API_BASE='http://127.0.0.1:8000'
```

## Implemented routes

- `/`
- `/workspace/translate`
- `/workspace/guide`
- `/workspace/character`
- `/workspace/relation`

## Verification

```powershell
npm run typecheck
npm run build
```
