'use strict';
// 카카오맵은 지도 렌더링만 담당합니다. 데이터·경계 가공과 제공은 Python에서 처리합니다.
const REGIONS = ['정릉동', '길음동', '장위동'];
const state = { region: '전체', stance: '전체', query: '', records: [], summary: null, map: null, shapes: [], labels: [], bounds: {}, boundaries: null };
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const kind = s => s === '긍정' ? 'positive' : 'negative';

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function regionSummary(region) {
  if (region === '전체') {
    return {records: state.summary.total_records,positive: state.summary.total_positive,negative: state.summary.total_negative};
  }
  return state.summary.by_region[region];
}
function visibleRecords() {
  const q = state.query.trim().toLocaleLowerCase();
  return state.records.filter(r =>
    (state.region === '전체' || r.region === state.region) &&
    (state.stance === '전체' || r.stances.includes(state.stance)) &&
    (!q || [r.speaker, r.title, r.summary, r.full_text, r.region, ...r.points.map(p=>p.theme)]
      .join(' ').toLocaleLowerCase().includes(q))
  );
}
function setRegion(region) {
  if (region !== '전체' && !REGIONS.includes(region)) return;
  state.region = region;
  $$('.region-btn').forEach(b => { const chosen = b.dataset.region === region; b.classList.toggle('active', chosen); b.setAttribute('aria-pressed', chosen); });
  refreshMapStyles();
  refreshList();
}
function setStance(stance) {
  if (!['전체','긍정','부정'].includes(stance)) return;
  state.stance = stance;
  $$('.filter-btn').forEach(b => { const chosen = b.dataset.stance === stance; b.classList.toggle('active', chosen); b.setAttribute('aria-pressed', chosen); });
  refreshList();
}
function buildRegionCards() {
  const slot = $('#regionCards'); slot.replaceChildren();
  REGIONS.forEach(region => {
    const s = regionSummary(region), totalTags = s.positive + s.negative;
    const button = el('button', 'region-mini'); button.type='button'; button.setAttribute('aria-label', `${region} 구술 ${s.records}건, 긍정 ${s.positive}, 부정 ${s.negative}`);
    const top = el('div','mini-top'); top.append(el('span','',region)); const arrow=el('span','arrow','↗'); top.append(arrow);
    const bars=el('div','mini-bars'); const pos=el('span','bar-pos'); const neg=el('span','bar-neg'); pos.style.width = `${totalTags ? 100*s.positive/totalTags : 0}%`; neg.style.width=`${totalTags ? 100*s.negative/totalTags : 0}%`; bars.append(pos,neg);
    const bottom=el('div','mini-bottom');
    for (const [label,count] of [['기록',s.records],['긍정',s.positive],['부정',s.negative]]) {
      const span=el('span',''); span.append(document.createTextNode(label+' '),el('b','',count)); bottom.append(span);
    }
    button.append(top,bars,bottom); button.addEventListener('click',()=> {setRegion(region); if (state.map && state.bounds[region]) state.map.setBounds(state.bounds[region]);});
    slot.append(button);
  });
}
function refreshList() {
  if (!state.summary) return;
  const s = regionSummary(state.region);
  $('#archiveHeading').textContent = state.region === '전체' ? '세 지역의 목소리' : `${state.region}의 목소리`;
  $('#archiveHint').textContent = state.region === '전체'
    ? '지역을 선택하면 해당 동네의 목소리만 볼 수 있습니다.'
    : `${state.region} 구술 자료 ${s.records}건의 긍정·부정 반응을 구분해서 살펴보세요.`;
  $('#allFilterCount').textContent = s.records;
  $('#positiveFilterCount').textContent = s.positive;
  $('#negativeFilterCount').textContent = s.negative;
  const records = visibleRecords();
  $('#recordCount').textContent = `${records.length}건`;
  const list = $('#archiveList'); list.replaceChildren();
  if (!records.length) {
    const empty = el('div','empty-state'); empty.append(el('strong','','해당하는 구술 자료가 없습니다.'),el('p','','다른 지역이나 반응 유형을 선택해 보세요.')); list.append(empty);
  }
  records.forEach(r => list.append(makeRecordCard(r)));
  $$('.region-mini').forEach(b => b.classList.toggle('active', state.region !== '전체' && b.textContent.startsWith(state.region)));
}
function makeRecordCard(r) {
  const card = el('article','record-card');
  const top = el('div','record-card-top');
  top.append(el('span','record-region',`${r.region} / 기록 ${String(r.id).padStart(2,'0')}`), el('span','page-tag', `자료 ${r.start_page}${r.start_page===r.end_page ? '' : '–'+r.end_page}쪽`));
  card.append(top,el('h3','record-title',r.title));
  const pts = r.points.filter(p => state.stance === '전체' || p.stance === state.stance);
  pts.forEach(p => {
    const q = el('div','record-quote '+kind(p.stance));
    q.append(el('span','stance-label '+kind(p.stance),`${p.stance} · ${p.theme}`));
    q.append(el('div','quote-text','“'+p.excerpt+'”'));
    card.append(q);
  });
  card.append(el('p','record-summary',r.summary));
  const bottom = el('div','record-bottom'); bottom.append(el('span','speaker',r.speaker));
  const details = el('details','record-details');
  details.append(el('summary','','원문 전체 보기'),el('p','',r.full_text));
  bottom.append(details); card.append(bottom);
  return card;
}
function regionFromPolygon(feature) { return feature.properties.region; }

function refreshMapStyles() {
  if (!state.map) return;
  for (const s of state.shapes) {
    const isSelected = state.region !== '전체' && s.region === state.region;
    const isDim = state.region !== '전체' && !isSelected;
    s.polygon.setOptions({
      fillColor: isSelected ? '#327f6f' : '#a4c9bd',
      fillOpacity: isSelected ? 0.56 : (isDim ? 0.10 : .34),
      strokeColor: isSelected ? '#205f54' : '#5e9184',
      strokeWeight: isSelected ? 3 : 2,
      strokeOpacity: isDim ? 0.30 : .94
    });
  }
  for (const label of state.labels) label.button.classList.toggle('active', state.region === label.region);
}
function iteratePolygons(geom) {
  return geom.type === 'Polygon' ? [geom.coordinates] : geom.type === 'MultiPolygon' ? geom.coordinates : [];
}
function fillMapBoundaries(collection) {
  const kakaoMap = state.map;
  const allBounds = new kakao.maps.LatLngBounds();
  const regionalBounds = Object.fromEntries(REGIONS.map(r=>[r,new kakao.maps.LatLngBounds()]));
  state.shapes = []; state.labels=[]; state.bounds=regionalBounds;
  collection.features.forEach(feature => {
    const region = regionFromPolygon(feature);
    for (const polygonCoordinates of iteratePolygons(feature.geometry)) {
      // 행정동 외곽선을 지도에 적용. Kakao Polygon은 [lat, lng]로 입력합니다.
      const outer = polygonCoordinates[0];
      if (!outer || outer.length < 3) continue;
      const path = outer.map(([lng,lat]) => {
        const xy = new kakao.maps.LatLng(lat,lng);
        allBounds.extend(xy); regionalBounds[region].extend(xy); return xy;
      });
      const polygon = new kakao.maps.Polygon({map:kakaoMap,path,strokeWeight:2,strokeColor:'#5e9184',strokeOpacity:.95,fillColor:'#a4c9bd',fillOpacity:.34});
      kakao.maps.event.addListener(polygon,'click',()=>setRegion(region));
      kakao.maps.event.addListener(polygon,'mouseover',()=> {if (state.region==='전체') polygon.setOptions({fillOpacity:.57,strokeWeight:3});});
      kakao.maps.event.addListener(polygon,'mouseout',refreshMapStyles);
      state.shapes.push({region,polygon});
    }
  });
  REGIONS.forEach(region=> {
    const bounds = regionalBounds[region];
    const pos = new kakao.maps.LatLng((bounds.getSouthWest().getLat()+bounds.getNorthEast().getLat())/2,(bounds.getSouthWest().getLng()+bounds.getNorthEast().getLng())/2);
    const button = el('button','map-region-label',region); button.type='button';
    button.addEventListener('click',()=>setRegion(region));
    const overlay = new kakao.maps.CustomOverlay({map:kakaoMap,position:pos,content:button,xAnchor:.5,yAnchor:.5,zIndex:5,clickable:true});
    state.labels.push({region,overlay,button});
  });
  kakaoMap.setBounds(allBounds);
  refreshMapStyles();
}
function showMapMessage(message, error=false) {
  $('#mapMessage').textContent = message;
  $('#mapPlaceholder').classList.remove('hidden');
  $('#mapPlaceholder').querySelector('h3').textContent = error ? '지도 경계를 표시하지 못했습니다' : '카카오 지도 연결 안내';
  $('#mapPlaceholder').querySelector('code').hidden = error;
}
async function initMap() {
  const config = await fetch('/api/config').then(r=>r.json());
  if (!config.has_key || config.kakao_js_key === 'YOUR_JAVASCRIPT_KEY_HERE') {
    showMapMessage('카카오디벨로퍼스에서 카카오맵을 활성화하고 JavaScript SDK 도메인을 등록한 후, .env 파일에 JavaScript 키를 입력해 주세요. 오른쪽의 구술 자료는 지금도 탐색할 수 있습니다.');
    return;
  }
  await new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.src=`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(config.kakao_js_key)}&autoload=false`;
    script.onload=resolve; script.onerror=()=>reject(Error('카카오 SDK가 로드되지 않았습니다. 키·도메인 등록·카카오맵 활성화 상태를 확인하세요.'));
    document.head.append(script);
  });
  if (!window.kakao || !kakao.maps) throw Error('카카오맵이 초기화되지 않았습니다.');
  await new Promise(resolve=>kakao.maps.load(resolve));
  state.map = new kakao.maps.Map($('#map'),{
    center:new kakao.maps.LatLng(37.611,127.029),level:6,
    draggable:true,scrollwheel:true
  });
  state.map.addControl(new kakao.maps.ZoomControl(),kakao.maps.ControlPosition.RIGHT);
  const res=await fetch('/api/boundaries');
  const data=await res.json();
  if (!res.ok) throw Error(data.detail ? `행정경계 내려받기 실패: ${data.detail}` : '행정경계 데이터를 가져올 수 없습니다.');
  if (data.features.length !== 9) throw Error('9개 행정동 경계가 확인되지 않았습니다.');
  state.boundaries=data;
  fillMapBoundaries(data);
  $('#mapPlaceholder').classList.add('hidden');
}
async function start() {
  try {
    const [recordsRes,summaryRes]=await Promise.all([fetch('/api/records'),fetch('/api/summary')]);
    if (!recordsRes.ok||!summaryRes.ok) throw Error('자료를 불러오지 못했습니다.');
    state.records=await recordsRes.json(); state.summary=await summaryRes.json();
    buildRegionCards();refreshList();
    $$('.region-btn').forEach(b=>b.addEventListener('click',()=> {setRegion(b.dataset.region);if(state.map){if(b.dataset.region==='전체' && state.boundaries){const bounds=new kakao.maps.LatLngBounds();state.boundaries.features.forEach(f=>iteratePolygons(f.geometry).forEach(p=>p[0].forEach(([lng,lat])=>bounds.extend(new kakao.maps.LatLng(lat,lng)))));state.map.setBounds(bounds);}else if(state.bounds[b.dataset.region])state.map.setBounds(state.bounds[b.dataset.region]);}}));
    $$('.filter-btn').forEach(b=>b.addEventListener('click',()=>setStance(b.dataset.stance)));
    $('#searchInput').addEventListener('input',e=>{state.query=e.target.value;refreshList();});
  } catch(e) {
    $('#archiveList').append(el('div','empty-state',`자료 로딩 오류: ${e.message}`));
  }
  try { await initMap(); }
  catch(e) { console.error(e);showMapMessage(e.message,true); }
}
document.addEventListener('DOMContentLoaded',start);
