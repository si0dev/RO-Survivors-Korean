# 레거시 번역 추가 대조 (2026-11-25)

기존 본편·특성 원본 추출본(빌드 `6b5475ee1`), 위키·소식 전체 추출본 및 정식 번역을 대조했습니다. 이 문서는 검수 기록이며 실행용 사전이 아닙니다.

- 기존 추출 대상에서 정식 레코드로 확인: 910개.
- 추가 조사 291개: 217개는 이미 원문 해시 또는 항목 ID가 존재하는 정식 레코드, 9개는 카드 리소스에서 발견한 신규 레코드, 9개는 보안 질문 선택지에서 원문 발견, 3개는 기타 소스 문맥에서 발견, 53개는 확보한 추출본에서 동일 원문 미확인.
- 기존 사전 전체는 이전 개발 기록에 보존합니다.
- 217개는 정식 레코드 존재 여부를 확인한 결과이며 해당 키가 현재 화면에 실제 표시되는지까지 검증한 것은 아닙니다.

## 원문 확인 및 통합: 카드 9개

`manifest.cards`에서 정확한 이름을 확인했고 누락된 카드 추출 경로를 추가했습니다.

| 기존 원문 | 기존 번역 |
| --- | --- |
| Baphomet Card | 바포메트 카드 |
| Chonchon Card | 촌촌 카드 |
| Goblin Card | 고블린 카드 |
| Kobold Card | 코볼트 카드 |
| Orc Hero Card | 오크히어로 카드 |
| Orc Skeleton Card | 오크 스켈레톤 카드 |
| Osiris Card | 오시리스 카드 |
| Pecopeco Egg Card | 페코페코 알 카드 |
| Pupa Card | 푸파 카드 |

카드 리소스의 나머지 89개도 동일 원문 해시의 기존 정식 번역을 이름 레코드에 연결했습니다. 카드 98개 전체를 검증했으며, 최종 정식 레코드는 7,990개입니다. 이 중 89개는 새 번역 문구가 아니라 기존 검증 번역을 새로 확인한 카드 이름 식별자에 연결한 것입니다.

## 원문 발견, 적용 범위 확인 필요: 12개

보안 질문 선택지 9개는 계정 복구 기능의 별도 표시 범위이므로 값을 변경하지 않습니다.

| 원문 | 기존 번역 |
| --- | --- |
| Super Novice | 슈퍼 노비스 |
| Dragonfly | 드래곤플라이 |
| Swordfish | 소드피쉬 |
| Dokkaebi | 도깨비 |
| Payon | 페이욘 |
| Geffen | 게펜 |
| Morroc | 모로크 |
| Alberta | 알베르타 |
| Izlude | 이즈루드 |

기타 소스 문맥 3개:

| 원문 | 기존 번역 | 근거 |
| --- | --- | --- |
| Group | 파티 | 내부 렌더러 타입 이름; UI 문구 근거 아님 |
| Bleeding | 출혈 | 리소스 설명 배열 내 문자열 |
| Search | 검색 | 본편의 직접 다국어 호출 영어 인수 |

## 동일 원문 미확인: 53개

정확한 원문과 적용 위치가 확인되기 전에는 승인하지 않습니다. 번역이 같거나 비슷한 것만으로 원문이 동일하다고 판정하지 않습니다.

| 기존 키 | 기존 번역 |
| --- | --- |
| Savage Bebe | 세비지 베베 |
| Byalan | 바이아란 |
| Prontera Sewers | 프론테라 지하수로 |
| Kafra | 카프라 |
| Defaults | 기본값 |
| Loading assets… | 리소스 불러오는 중… |
| Character selection | 캐릭터 선택 |
| Character Selection | 캐릭터 선택 |
| Change character | 캐릭터 변경 |
| Log out | 로그아웃 |
| Logout | 로그아웃 |
| Login | 로그인 |
| Log in | 로그인 |
| Sign in | 로그인 |
| Save and log in | 저장 후 로그인 |
| Sex | 성별 |
| Male | 남성 |
| Hombre | 남성 |
| Female | 여성 |
| Mujer | 여성 |
| Class | 직업 |
| Statistics | 스탯 |
| Points remaining | 남은 포인트 |
| Puntos restantes | 남은 포인트 |
| Available points | 사용 가능한 포인트 |
| In run | 전투 중 |
| Return to Prontera | 프론테라로 돌아가기 |
| Completed | 완료 |
| Delete all | 모두 삭제 |
| Trading | 거래 중 |
| Reject | 거절 |
| Minerals | 광석 |
| The trade has been cancelled. | 거래가 취소되었습니다. |
| Noon | 정오 |
| Sunset | 해질녘 |
| Magic Attack | 마법 공격력 |
| Defense | 방어력 |
| Magic Defense | 마법 방어력 |
| Hit rate | 명중률 |
| Consumables | 소비 아이템 |
| Refinement | 제련 |
| Price | 가격 |
| Quantity | 수량 |
| Confirm | 확인 |
| Yes | 예 |
| Next | 다음 |
| Save | 저장 |
| Shop | 상점 |
| Storage | 창고 |
| Help | 도움말 |
| Exit | 나가기 |
| Prontera awaits you | 프론테라가 여러분을 기다립니다 |
| Fountain square | 분수 광장 |

## 후속 집중 검수 및 처리 결정

- 추가 추출 2회(65개 및 47개)와 정식 레코드 7,990개를 대조했습니다. 원문 변형에 대응하는 기존 번역은 유지합니다. 유사어만으로 동일 UI라고 확정하지 않습니다.
- 위키 검색 결과 제목: 본편 `main-BxZDCw8d.js`의 `wk-detail` 생성 코드에서 직접 다국어 호출의 스페인어 `Búsqueda`와 영어 `Search`를 확인했습니다. 두 원문을 위키 전용 레코드로 추가합니다(검색). 기존 검색 입력창 번역은 유지합니다.
- `Bleeding`은 리소스에 존재하지만 표시 여부 미확인으로 보류합니다. 보안 질문, 내부 식별자 및 나머지 미확인 레거시 키는 이관하지 않습니다. 미확인은 미사용 확정을 뜻하지 않습니다.
- 레거시 실행 사전은 복원하지 않습니다. 정식 레코드 7,992개를 유지하며 엔진 버전은 변경하지 않습니다. 전체 실제 플레이 화면의 검증을 완료했다는 의미는 아닙니다.
