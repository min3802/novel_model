# w.LiGHTER Django Server

웹소설 현지화 보조 서비스 **w.LiGHTER**의 Django 서버 프로젝트입니다.

현재 단계는 최종 기능 구현 전, 요구사항 정의서를 기준으로 앱 구조와 화면 URL 틀을 잡아둔 상태입니다.

## 1. 프로젝트 실행 방법

### 1. 가상환경 활성화

conda를 사용하는 경우:

```bash
conda activate wlighter
```

venv를 사용하는 경우:

```bash
.\.venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. DB 반영

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. 서버 실행

```bash
python manage.py runserver
```

접속 주소:

```txt
http://127.0.0.1:8000/
```

관리자 페이지:

```txt
http://127.0.0.1:8000/admin/
```

## 2. 앱 구조

```txt
accounts     사용자 인증, 회원정보, 회원탈퇴
works        작품 등록, 작품 목록, 작품 상세, 회차 관리
characters   캐릭터 설정집
translation  번역 실행, 검수 챗봇, 번역 결과 버전 관리
relationships 캐릭터 관계도 HTML 생성/조회/삭제
covers       표지 이미지 생성/조회/삭제
guides        현지화 가이드 생성/조회/다운로드/삭제
credits      크레딧 충전, 조회, 차감, 결제 취소
```

## 3. 현재 완료된 내용

```txt
- Django 프로젝트 생성
- 앱 분리
- settings.py 앱 등록
- URL 연결
- base.html 공통 템플릿 구성
- static CSS 연결
- 기본 모델 작성
- admin 등록
- requirements.txt 생성
- 요구사항 ID 기준 HTML 화면 틀 생성
```

현재 HTML 화면은 실제 기능 구현 전, 요구사항별 화면 위치를 확인하기 위한 틀입니다.

## 4. 주요 모델

```txt
works
- Work
- Episode

characters
- Character

translation
- TranslationResult
- ChatMessage

relationships
- RelationMap

guides
- LocalizationGuide

covers
- Cover

credits
- Plan
- Payment
- CreditTransaction
```

## 5. 요구사항별 화면 URL

### 사용자 관리

```txt
REQ-AUTH-001 로그인
/accounts/login/

REQ-AUTH-002 로그아웃
/accounts/logout/

REQ-USER-001 회원가입
/accounts/signup/

REQ-USER-002 회원정보 조회
/accounts/profile/

REQ-USER-003 회원정보 수정
/accounts/profile/edit/

REQ-USER-004 회원탈퇴
/accounts/withdraw/
```

### 작품 관리

```txt
REQ-WORK-001 작품 등록
/works/new/

REQ-WORK-002 작품 목록 조회
/works/

REQ-WORK-003 작품 상세
/works/<work_id>/

REQ-WORK-004 작품 정보 수정
/works/<work_id>/edit/

REQ-WORK-005 작품 삭제
/works/<work_id>/delete/
```

### 회차 관리

```txt
REQ-CHAP-001 회차 등록
/works/<work_id>/episodes/new/

REQ-CHAP-002 회차 목록 조회
/works/<work_id>/episodes/

REQ-CHAP-003 회차 상세 조회
/works/<work_id>/episodes/<episode_id>/

REQ-CHAP-004 회차 수정
/works/<work_id>/episodes/<episode_id>/edit/

REQ-CHAP-005 회차 삭제
/works/<work_id>/episodes/<episode_id>/delete/
```

### 번역 / 검수

```txt
REQ-CHAP-006 번역 실행
/translation/episodes/<episode_id>/run/

REQ-CHAP-007 검수 챗봇
/translation/results/<translation_id>/chat/

REQ-CHAP-008 번역 결과 버전 조회
/translation/episodes/<episode_id>/results/

REQ-CHAP-009 번역 결과 버전 삭제
/translation/results/<translation_id>/delete/
```

### 캐릭터 설정집

```txt
REQ-UNIV-001 캐릭터 설정 생성
/characters/new/

REQ-UNIV-002 캐릭터 설정 목록 조회
/characters/

REQ-UNIV-003 캐릭터 설정 상세 조회
/characters/<character_id>/

REQ-UNIV-004 캐릭터 설정 수정
/characters/<character_id>/edit/

REQ-UNIV-005 캐릭터 설정 삭제
/characters/<character_id>/delete/
```

### 표지 이미지

```txt
REQ-VIS-001 표지 이미지 생성
/covers/works/<work_id>/covers/new/

REQ-VIS-002 표지 이미지 조회
/covers/works/<work_id>/covers/

REQ-VIS-003 표지 이미지 삭제
/covers/works/<work_id>/covers/<image_id>/delete/
```

### 캐릭터 관계도

```txt
REQ-VIS-004 캐릭터 관계도 생성
/relationships/new/

REQ-VIS-005 캐릭터 관계도 조회
/relationships/

REQ-VIS-006 캐릭터 관계도 상세조회
/relationships/<map_id>/

REQ-VIS-007 캐릭터 관계도 다운로드
/relationships/<map_id>/download/

REQ-VIS-008 캐릭터 관계도 삭제
/relationships/<map_id>/delete/
```

### 현지화 가이드

```txt
REQ-GDE-001 현지화 가이드 생성
/guides/new/

REQ-GDE-002 현지화 가이드 조회
/guides/

REQ-GDE-003 현지화 가이드 상세조회
/guides/<guide_id>/

REQ-GDE-004 현지화 가이드 다운로드
/guides/<guide_id>/download/

REQ-GDE-005 현지화 가이드 삭제
/guides/<guide_id>/delete/
```

### 결제 / 크레딧

```txt
REQ-CRED-001 크레딧 충전
/credits/charge/

REQ-CRED-002 잔여 크레딧 조회
/credits/balance/

REQ-CRED-003 크레딧 차감
/credits/use/

REQ-CRED-004 결제 취소
/credits/cancel/
```

## 6. 아직 미구현인 내용

```txt
- 실제 소셜 로그인 연동
- 작품/회차 CRUD 저장 로직
- 파일 업로드 처리
- 번역 API 연동
- 검수 챗봇 기능
- 캐릭터 설정 CRUD
- 관계도 HTML 생성 로직
- 표지 이미지 생성 API 연동
- 현지화 가이드 생성 로직
- Toss Payments 결제 연동
- 크레딧 차감 트랜잭션 처리
```

## 7. 다음 구현 추천 순서

```txt
1. 작품 등록 / 목록 / 상세
2. 회차 등록 / 목록 / 상세
3. 캐릭터 설정집 CRUD
4. 번역 실행 및 결과 저장
5. 검수 챗봇
6. 현지화 가이드
7. 관계도 HTML 생성
8. 표지 이미지 생성
9. 크레딧 / 결제
```

## 8. 개발 메모

현재 화면은 요구사항 추적을 위한 분리형 구조입니다.
최종 UI 구현 시에는 등록, 수정, 삭제 화면을 모달 또는 partial 템플릿으로 합칠 수 있습니다.

```txt
초기 구조: 요구사항 ID별 화면 분리
최종 구조: 사용자 흐름 기준으로 화면 통합 가능
```
