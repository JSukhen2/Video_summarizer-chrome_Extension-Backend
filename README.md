# Video Analyzer Backend

OpenAI Whisper + Gemini 2.5 Flash 하이브리드 동영상 분석 서버

## 기능

- **비디오 업로드**: 동영상 파일을 받아서 분석
- **Whisper STT**: OpenAI Whisper API로 음성을 텍스트로 변환
- **Gemini 분석**: 비디오와 스크립트를 함께 Gemini로 분석
- **질의응답**: 비디오 내용 기반 Q&A + 인터넷 검색

## 환경 설정

`.env` 파일을 생성하고 다음 키를 설정하세요:

```env
OPENAI_API_KEY=sk-your-openai-key-here
GEMINI_API_KEY=your-gemini-key-here
TAVILY_API_KEY=your-tavily-key-here  # 선택사항
FLASK_ENV=production
```

## 로컬 실행

```bash
pip install -r requirements.txt
python app.py
```

## Render 배포

1. Render.com에 GitHub 저장소 연결
2. 새 Web Service 생성
3. 환경 변수 설정 (OPENAI_API_KEY, GEMINI_API_KEY 등)
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 300`

## API 엔드포인트

### POST /analyze
비디오 파일을 업로드하여 분석

**Request:**
- `video`: 비디오 파일 (multipart/form-data)

**Response:**
```json
{
  "success": true,
  "transcript": {
    "text": "전체 스크립트",
    "segments": [...]
  },
  "analysis": {
    "summary": "요약",
    "tableOfContents": [...],
    "keywords": [...],
    "keyInsights": [...]
  }
}
```

### POST /qa
질의응답

**Request:**
```json
{
  "question": "질문",
  "transcript": {...},
  "analysis": {...}
}
```

**Response:**
```json
{
  "success": true,
  "answer": "답변"
}
```

## 주의사항

- MoviePy는 FFmpeg가 필요합니다. Render에서는 자동으로 설치됩니다.
- 큰 비디오 파일은 처리 시간이 오래 걸릴 수 있습니다 (timeout 300초 설정).

