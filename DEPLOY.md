# Render 배포 가이드

## 1. GitHub 저장소 준비

1. 백엔드 코드를 GitHub에 푸시
2. `backend/` 디렉토리가 루트에 있는지 확인

## 2. Render에서 서비스 생성

1. [Render Dashboard](https://dashboard.render.com) 접속
2. "New +" → "Web Service" 클릭
3. GitHub 저장소 연결
4. 설정:
   - **Name**: `video-analyzer-backend`
   - **Root Directory**: `backend` (중요!)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 300`

## 3. 환경 변수 설정

Render Dashboard → Environment Variables에서 다음 추가:

```
OPENAI_API_KEY=sk-your-key
GEMINI_API_KEY=your-gemini-key
TAVILY_API_KEY=your-tavily-key (선택사항)
FLASK_ENV=production
```

## 4. 배포 확인

배포 완료 후:
- `https://your-service.onrender.com/health` 접속하여 `{"status": "ok"}` 확인

## 5. Chrome Extension 설정

`.env` 파일에 백엔드 URL 추가:

```
BACKEND_API_URL=https://your-service.onrender.com
```

## 주의사항

- Render 무료 티어는 15분 비활성 시 슬립 모드로 전환됩니다
- 첫 요청 시 약간의 지연이 있을 수 있습니다
- 큰 비디오 파일은 처리 시간이 오래 걸릴 수 있습니다

