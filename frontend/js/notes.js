// 차트 옆 설명 문장 만들기 (index.html 전용, charts.js 다음에 읽는다)
// 문장에 들어가는 숫자는 모두 data/factor_sample.json 에서 계산한다. 원인·전망 같은 해석은 쓰지 않고,
// 해석이 필요한 곳은 데이터사전(drivers.json)의 '예상 부호'만 근거로 쓴다.

// 변화 표현: 월별 → 전년동월, 그 밖 → 전년동기
const changeName = (m) => (m.freq === "M" ? "전년동월 대비" : "전년동기 대비");
const RECENT = { M: 36, Q: 12, H: 6, A: 3 }; // '최근 3년' 의 관측 개수

// 최근 3년 안에서 최신값의 위치
function recentPosition(m, region) {
  const end = provisionalIndex(m);
  const values = (m.series[region] || []).slice(0, end);
  const window = values.slice(-RECENT[m.freq]).filter((v) => v != null);
  if (window.length < 3) return null;
  const last = window[window.length - 1];
  const lo = Math.min(...window);
  const hi = Math.max(...window);
  if (hi === lo) return null;
  if (last === hi) return "최근 3년 최고";
  if (last === lo) return "최근 3년 최저";
  const pos = (last - lo) / (hi - lo);
  return pos >= 2 / 3 ? "최근 3년 범위의 상단" : pos <= 1 / 3 ? "최근 3년 범위의 하단" : "최근 3년 범위의 중간";
}

// 최근 3개 관측(월이면 3개월) 동안의 방향
function recentDirection(m, region) {
  const end = provisionalIndex(m);
  const values = (m.series[region] || []).slice(0, end).filter((v) => v != null);
  if (values.length < 4) return null;
  const a = values[values.length - 4];
  const b = values[values.length - 1];
  const unitName = { M: "개월", Q: "분기", H: "반기", A: "년" }[m.freq];
  const span = `최근 3${unitName}`;
  const tiny = Math.abs(a) * 0.001;
  if (Math.abs(b - a) <= tiny) return `${span} 보합`;
  return `${span} ${b > a ? "상승" : "하락"}`;
}

// 데이터사전 예상 부호로 읽은 방향: +는 값이 오를 때 월세 리스크가 커지는 쪽, -는 그 반대
function signReading(v, change) {
  if (!v?.sign || change == null || change === 0) return null;
  if (v.sign === "±" || v.sign === "+/-") return "예상 부호가 ±라 방향 해석은 국면에 따라 달라집니다.";
  const up = change > 0;
  const riskUp = v.sign === "+" ? up : !up;
  return `데이터사전 예상 부호(${v.sign}) 기준으로는 월세 리스크를 ${riskUp ? "키우는" : "낮추는"} 쪽의 변화입니다.`;
}

// 차트 한 개의 머리기사와 본문 문장들
// v: drivers.json 의 변수, m: factor_sample 계열, region: 지역 이름
function describe(v, m, region) {
  const l = latestOf(m, region);
  const name = m.label.replace(/^(국토부실거래|주민등록인구|인구이동|주택건설|소비자동향조사|부동산원)\s*/, "").replace(/\((구지수연결|권역역산 학습용)\)$/, "");
  if (!l) return { headline: `${region} ${name}: 샘플 기간에 값이 없습니다`, body: [] };

  const value = fmtValue(l.value, m.unit);
  const chg = l.change != null ? `${changeName(m)} ${fmtChange(l.change, l.mode, m.unit)}` : null;
  const pos = recentPosition(m, region);
  const headline = `${region} ${name} ${value}${chg ? `, ${chg}` : ""}${pos === "최근 3년 최고" || pos === "최근 3년 최저" ? ` (${pos})` : ""}`;

  const body = [];
  const facts = [`${periodLabel(l.period, true)} 기준 ${value}`];
  if (chg) facts.push(chg);
  const dir = recentDirection(m, region);
  if (dir) facts.push(dir);
  body.push(`${facts.join(", ")}입니다.`);
  if (pos && pos !== "최근 3년 최고" && pos !== "최근 3년 최저") body.push(`현재 수준은 ${pos}에 있습니다.`);
  const reading = signReading(v, l.change);
  if (reading) body.push(reading);
  return { headline, body, latest: l };
}

// 변수 설명 (데이터사전 항목을 문장으로)
function variableProse(v) {
  const parts = [];
  if (v.sign === "+") parts.push("값이 오르면 월세 리스크가 커지는 방향(+)으로 분류합니다.");
  else if (v.sign === "-") parts.push("값이 오르면 월세 리스크가 줄어드는 방향(−)으로 분류합니다.");
  else if (v.sign) parts.push("국면에 따라 방향이 달라지는 변수(±)로 분류합니다.");
  if (v.lead) parts.push(`기대 선행성은 ${v.lead}입니다.`);
  if (v.transform) parts.push(`분석 때는 ${v.transform} 형태로 가공해 쓰기를 권장합니다.`);
  if (v.leakage && v.leakage !== "낮음") parts.push(`목표변수와 같은 달 값을 쓰면 정보 누출(Leakage) 위험이 ${v.leakage}입니다.`);
  return parts.join(" ");
}

// 자료 표기: '자료: 출처 · DFMBA 전처리본'
function sourceLine(v, m) {
  const src = (m?.source || v?.source || "").split(/\s*[\/|]\s*/)[0];
  return `자료: ${src ? src + ", " : ""}DFMBA 전처리본(1차_결측보완)`;
}
