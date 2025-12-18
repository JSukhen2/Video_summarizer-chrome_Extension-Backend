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

### ⚠️ 중요: API 키는 절대 GitHub에 커밋하지 마세요!

### 로컬 개발 환경
1. `env.example` 파일을 참고하여 `.env` 파일 생성
2. 실제 API 키 값을 입력 (`.env` 파일은 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않습니다)

### Render 배포 환경
Render Dashboard → Environment → Environment Variables에서 다음 변수들을 **개별적으로** 추가:

| Key | Value | 필수 여부 | 설명 |
|-----|-------|----------|------|
| `OPENAI_API_KEY` | 실제 OpenAI API 키 | 필수 | [OpenAI Platform](https://platform.openai.com/api-keys)에서 발급 |
| `GEMINI_API_KEY` | 실제 Gemini API 키 | 필수 | [Google AI Studio](https://makersuite.google.com/app/apikey)에서 발급 |
| `TAVILY_API_KEY` | 실제 Tavily API 키 | 선택 | [Tavily](https://tavily.com/)에서 발급 (인터넷 검색 기능 사용 시 필요) |
| `FLASK_ENV` | `production` | 필수 | Flask 환경 모드 (문자열 그대로 `production` 입력) |

**각 변수 설명:**

1. **OPENAI_API_KEY**: OpenAI API 키
   - 발급: https://platform.openai.com/api-keys
   - 로그인 후 "Create new secret key" 클릭

2. **GEMINI_API_KEY**: Google Gemini API 키
   - 발급: https://makersuite.google.com/app/apikey
   - Google 계정으로 로그인 후 API 키 생성

3. **TAVILY_API_KEY**: Tavily 인터넷 검색 API 키 (선택사항)
   - 발급: https://tavily.com/
   - 회원가입 후 API 키 발급
   - **없어도 작동하지만**, 비디오 외부 정보 검색 기능을 사용하려면 필요합니다
   - 설정하지 않으면 인터넷 검색 기능만 비활성화됩니다

4. **FLASK_ENV**: Flask 환경 설정
   - 값: `production` (문자열 그대로 입력)
   - 외부에서 가져오는 것이 아니라 직접 입력하는 값입니다

**주의사항:**
- Render에서는 각 환경 변수를 Key-Value 쌍으로 개별 추가합니다
- `=` 기호는 포함하지 않고, Key와 Value를 분리하여 입력합니다
- 예: Key = `OPENAI_API_KEY`, Value = `sk-actual-key-here`

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

