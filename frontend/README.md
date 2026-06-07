# w.LiGHTER Next.js Frontend

Reference-image oriented UI replacement for the previous Streamlit screens.

## Run

Terminal 1, Python API:

기본은 실제 모드(실제 OpenAI 호출)로 동작한다. 실제 모드는 OPENAI_API_KEY가 필요하다.
mock(가짜 응답)으로 띄우려면 아래처럼 환경변수를 명시적으로 켠다:

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
