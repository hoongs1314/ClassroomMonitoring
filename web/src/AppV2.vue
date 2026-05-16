<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { message } from 'ant-design-vue';
import {
  DesktopOutlined,
  DashboardOutlined,
  BulbOutlined,
  TeamOutlined,
  AlertOutlined,
  BellOutlined,
  VideoCameraFilled,
  SafetyCertificateOutlined
} from '@ant-design/icons-vue';

const API_BASE = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws";

const state = ref({
  is_running: false,
  time: '--:--:--',
  img_w: 1920,
  img_h: 1080,
  seats: [],
  events: [],
  counts: { total: 0, focus: 0, normal: 0 }
});

const showDetail = ref(false);
const selectedEvent = ref(null);
const showFrameDetail = ref(false);
const latestFrameUrl = ref("");
const frameSeats = ref([]);
const showReminderList = ref(false);
const reminderTitle = ref("");
const reminderRisk = ref("");

let socket = null;
const connect = () => {
  socket = new WebSocket(WS_URL);
  socket.onmessage = (e) => state.value = JSON.parse(e.data);
  socket.onclose = () => setTimeout(connect, 2000);
};

const start = async () => {
  await fetch(`${API_BASE}/api/start`, { method: 'POST' });
  message.success('监测系统已激活');
};
const stop = async () => {
  await fetch(`${API_BASE}/api/stop`, { method: 'POST' });
  message.success('监测已停止');
};

const getDetailJson = (eventItem) => {
  try {
    const cleanRaw = eventItem.full_ans.replace(/```json|```/g, "").trim();
    const data = JSON.parse(cleanRaw);
    if (Array.isArray(data)) {
        const found = data.find(it => 
            it.seat_id == eventItem.box_id || 
            it.seat_code == eventItem.seat || 
            it.seat == eventItem.seat
        );
        return found ? JSON.stringify(found, null, 2) : cleanRaw;
    }
    return cleanRaw;
  } catch {
    return eventItem.full_ans;
  }
};

const openDetail = (e) => {
  selectedEvent.value = {
    ...e,
    display_json: getDetailJson(e)
  };
  showDetail.value = true;
};

const abnormalSeats = computed(() => state.value.seats.filter(s => ["HEAD_DOWN", "DESK_LYING"].includes(s.status)));
const reminderEvents = computed(() => state.value.events.filter(e => e.risk === reminderRisk.value));

const openFrameDetail = () => {
  latestFrameUrl.value = `${API_BASE}/api/latest_frame?t=${Date.now()}`;
  frameSeats.value = state.value.seats.map(s => ({
    ...s,
    box: [...s.box]
  }));
  showFrameDetail.value = true;
};

const openReminderList = (risk, title) => {
  reminderRisk.value = risk;
  reminderTitle.value = title;
  showReminderList.value = true;
};

onMounted(() => connect());
onUnmounted(() => socket?.close());

const getBoxStyle = (box) => {
  if (!box || !state.value.img_w) return {};
  return {
    left: `${(box[0] / state.value.img_w) * 100}%`,
    top: `${(box[1] / state.value.img_h) * 100}%`,
    width: `${((box[2] - box[0]) / state.value.img_w) * 100}%`,
    height: `${((box[3] - box[1]) / state.value.img_h) * 100}%`,
  };
};

const statusMap = {
  NORMAL: { c: '#16b45f', t: '正常' },
  HEAD_DOWN: { c: '#ff8a1f', t: '低头' },
  DESK_LYING: { c: '#ff3f45', t: '趴睡' },
  UNCERTAIN: { c: '#8c8c8c', t: '模糊' },
  SUSPECTED: { c: '#ff8a1f', t: '疑似' }
};
const getS = (s) => statusMap[s] || statusMap.NORMAL;
const mediaUrl = (url) => `${API_BASE}${url}`;
</script>

<template>
  <div class="screen">
    <header class="topbar">
      <div class="brand">
        <div class="icon"><VideoCameraFilled /></div>
        <div class="titles">
          <h1>课堂异常行为监测系统</h1>
          <p>AI 智能识别 · 实时预警 · 规范课堂秩序 · 提升教学质量</p>
        </div>
      </div>
      <div class="actions">
        <span :class="['status-tag', state.is_running ? 'cyan' : 'blue']">
          {{ state.is_running ? '正在监控' : '待启动' }}
        </span>
        <a-button v-if="!state.is_running" type="primary" @click="start">启动监控</a-button>
        <a-button v-else danger @click="stop">停止监控</a-button>
        <span class="clock">{{ state.time }}</span>
      </div>
    </header>

    <main class="main">
      <section class="panel stage-panel">
        <div class="bar">
          <h2><DesktopOutlined /> 主监控画面</h2>
          <div class="meta">LIVE <div :class="['dot', { active: state.is_running }]"></div> 在线</div>
        </div>
        <div class="box">
          <div class="viewport" :style="{ aspectRatio: `${state.img_w}/${state.img_h}` }">
            <div v-if="state.is_running" class="badge"><span></span> LIVE</div>
            <img v-if="state.is_running" src="http://localhost:8000/video_feed" class="feed" />
            <div v-else class="empty-feed">监控流已切断</div>
            <div v-for="s in abnormalSeats" :key="s.seat_id" class="rect" :style="[getBoxStyle(s.box), { borderColor: getS(s.status).c }]">
              <span :style="{ background: getS(s.status).c }">{{ s.seat_code }}</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="rail">
        <section class="panel stats-panel">
          <div class="bar">
            <h2><DashboardOutlined /> 实时统计</h2>
            <span class="link">今日数据</span>
          </div>
          <div class="stats-grid">
            <div class="stat-card stat-blue clickable" @click="openFrameDetail">
              <div class="stat-head">
                <div class="stat-icon"><TeamOutlined /></div>
                <div class="stat-label">学生人数</div>
              </div>
              <div class="stat-value">{{ state.counts.total }}</div>
              <div class="sparkline"></div>
            </div>
            <div class="stat-card stat-red clickable" @click="openReminderList('高', '重点提醒')">
              <div class="stat-head">
                <div class="stat-icon"><AlertOutlined /></div>
                <div class="stat-label">重点提醒</div>
              </div>
              <div class="stat-value">{{ state.counts.focus }}</div>
              <div class="sparkline"></div>
            </div>
            <div class="stat-card stat-blue clickable" @click="openReminderList('中', '普通提醒')">
              <div class="stat-head">
                <div class="stat-icon"><BellOutlined /></div>
                <div class="stat-label">普通提醒</div>
              </div>
              <div class="stat-value">{{ state.counts.normal }}</div>
              <div class="sparkline"></div>
            </div>
          </div>
        </section>

        <section class="panel alert-panel">
          <div class="bar">
            <h2><BulbOutlined /> 异常行为通知</h2>
            <span class="link">查看全部</span>
          </div>
          <div v-if="state.events.length" class="list">
            <article v-for="e in state.events" :key="e.id" class="item" @click="openDetail(e)">
              <div class="img-box">
                <img :src="mediaUrl(e.url)" />
                <span class="time">{{ e.time }}</span>
              </div>
              <div class="body">
                <div class="row">座位：{{ e.seat }}</div>
                <div class="row">异常：<strong>{{ e.label }}</strong></div>
                <p>{{ e.reason }}</p>
              </div>
              <div class="arrow">›</div>
            </article>
          </div>
          <div v-else class="empty-state">
            <SafetyCertificateOutlined class="e-icon" />
            <p>暂无异常</p>
          </div>
        </section>
      </aside>
    </main>

    <a-modal v-model:open="showDetail" title="异常行为详情复核" :footer="null" width="800px" centered>
      <div v-if="selectedEvent" class="detail-wrap">
        <div class="detail-main">
          <img :src="mediaUrl(selectedEvent.url)" class="detail-img" />
          <div class="detail-info">
            <p><b>学生座位：</b>{{ selectedEvent.seat }}</p>
            <p><b>检测时间：</b>{{ selectedEvent.time }}</p>
            <p><b>坐标位置：</b>{{ selectedEvent.box }}</p>
            <p><b>异常分型：</b><span style="color: #ff3f45; font-weight: 800;">{{ selectedEvent.label }}</span></p>
            <p><b>判定依据：</b>{{ selectedEvent.reason }}</p>
          </div>
        </div>
        <div class="detail-raw">
          <h4>大模型返回原文</h4>
          <pre>{{ selectedEvent.full_ans }}</pre>
        </div>
      </div>
    </a-modal>

    <a-modal v-model:open="showFrameDetail" title="最近完整课堂帧" :footer="null" width="980px" centered>
      <div class="frame-detail">
        <div class="frame-viewport" :style="{ aspectRatio: `${state.img_w}/${state.img_h}` }">
          <img v-if="latestFrameUrl" :src="latestFrameUrl" class="frame-img" />
          <div v-for="s in frameSeats" :key="s.seat_id" class="rect frame-rect" :style="[getBoxStyle(s.box), { borderColor: getS(s.status).c }]">
            <span :style="{ background: getS(s.status).c }">{{ s.seat_code }}</span>
          </div>
        </div>
      </div>
    </a-modal>

    <a-modal v-model:open="showReminderList" :title="reminderTitle" :footer="null" width="820px" centered>
      <div v-if="reminderEvents.length" class="modal-list">
        <article v-for="e in reminderEvents" :key="e.id" class="item" @click="openDetail(e)">
          <div class="img-box">
            <img :src="mediaUrl(e.url)" />
            <span class="time">{{ e.time }}</span>
          </div>
          <div class="body">
            <div class="row">座位：{{ e.seat }}</div>
            <div class="row">异常：<strong>{{ e.label }}</strong></div>
            <p>{{ e.reason }}</p>
          </div>
          <div class="arrow">›</div>
        </article>
      </div>
      <div v-else class="empty-state reminder-empty">
        <SafetyCertificateOutlined class="e-icon" />
        <p>暂无数据</p>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.screen { --blue: #1268f3; --red: #ff3f45; display: flex; flex-direction: column; height: 100vh; padding: 12px 22px; background: linear-gradient(135deg, rgba(218,236,255,0.9), rgba(248,252,255,0.7)), #f4f9ff; font-family: "Noto Sans SC", sans-serif; }

.topbar { position: relative; display: flex; justify-content: space-between; align-items: center; min-height: 96px; padding: 18px 28px; margin-bottom: 12px; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35,88,155,0.1); overflow: hidden; }
.topbar::after { content: ""; position: absolute; right: 44px; top: 14px; width: 360px; height: 88px; opacity: 0.3; background: radial-gradient(circle at 86% 50%, rgba(18,104,243,0.15), transparent 20%), repeating-radial-gradient(ellipse at 100% 50%, transparent 0 17px, rgba(18,104,243,0.1) 18px 19px); }
.brand { display: flex; align-items: center; gap: 22px; z-index: 1; }
.brand .icon { width: 50px; height: 50px; border-radius: 10px; color: #fff; font-size: 24px; background: linear-gradient(180deg, #0d6dff, #0758e8); display: flex; align-items: center; justify-content: center; box-shadow: 0 10px 20px rgba(18,104,243,0.24); }
.brand h1 { margin: 0; font-size: 30px; font-weight: 800; color: #0c234d; line-height: 1.1; }
.brand p { margin: 4px 0 0; font-size: 15px; color: #7083a2; font-weight: 500; }

.actions { display: flex; align-items: center; gap: 15px; z-index: 1; }
.status-tag { padding: 6px 16px; border-radius: 999px; font-size: 13px; font-weight: 700; border: 1px solid #cfe1fa; }
.status-tag.cyan { border-color: #bcebd2; background: #eefcf5; color: #14834b; }
.status-tag.blue { border-color: #cfe1fa; background: #f2f7ff; color: #31547f; }
.clock { font-size: 16px; font-weight: 700; color: #6d7f9c; min-width: 80px; }

.main { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(420px, 0.98fr); gap: 20px; flex: 1; min-height: 0; }
.rail { display: grid; grid-template-rows: auto 1fr; gap: 16px; min-height: 0; }

.panel { background: #fff; border-radius: 18px; border: 1px solid rgba(210,226,248,0.9); box-shadow: 0 18px 42px rgba(35,88,155,0.14); padding: 18px; display: flex; flex-direction: column; min-height: 0; }
.bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.bar h2 { display: flex; align-items: center; gap: 12px; color: #045be6; font-size: 22px; font-weight: 800; margin: 0; }
.meta { display: flex; align-items: center; gap: 12px; color: #617592; font-size: 15px; font-weight: 700; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #94a3b8; }
.dot.active { background: #16b45f; box-shadow: 0 0 0 4px rgba(22,180,95,0.12); }
.link { color: #6d7f9c; font-size: 14px; font-weight: 700; }

.box { position: relative; flex: 1; border-radius: 15px; overflow: hidden; background: #111; display: flex; align-items: center; justify-content: center; }
.viewport { position: relative; width: 100%; max-height: 100%; }
.feed { width: 100%; height: 100%; object-fit: contain; display: block; }
.empty-feed { height: 500px; display: flex; align-items: center; justify-content: center; color: #666; font-size: 18px; font-weight: 700; }
.badge { position: absolute; left: 20px; top: 20px; z-index: 3; display: flex; align-items: center; gap: 8px; padding: 0 15px; height: 34px; border-radius: 8px; background: #ff333d; color: #fff; font-weight: 800; font-size: 14px; }
.badge span { width: 8px; height: 8px; border-radius: 50%; background: #fff; animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: 0.3; } }

.rect { position: absolute; border: 2px solid #16b45f; background: rgba(22,180,95,0.08); pointer-events: none; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); z-index: 5; }
.rect span { position: absolute; top: -20px; left: -2px; padding: 0 8px; font-size: 12px; font-weight: 800; color: #fff; border-radius: 3px 3px 0 0; line-height: 20px; white-space: nowrap; }

.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stat-card { position: relative; min-height: 140px; padding: 16px; border-radius: 12px; border: 1px solid #b9d6ff; background: radial-gradient(circle at 100% 0, rgba(18,104,243,0.18), transparent 34%), linear-gradient(180deg, #f8fbff, #edf5ff); box-shadow: 0 10px 24px rgba(18, 104, 243, 0.1); }
.stat-card.clickable { cursor: pointer; }
.stat-card.clickable:hover { transform: translateY(-1px); box-shadow: 0 14px 28px rgba(18, 104, 243, 0.16); }
.stat-card.stat-red { border-color: #ffd3d6; background: radial-gradient(circle at 100% 0, rgba(255,63,69,0.18), transparent 34%), linear-gradient(180deg, #fff8f8, #fff1f2); }
.stat-head { display: flex; align-items: center; gap: 12px; min-height: 38px; margin-bottom: 8px; }
.stat-icon { width: 38px; height: 38px; border-radius: 50%; background: #e7f1ff; display: flex; align-items: center; justify-content: center; color: var(--blue); font-size: 23px; font-weight: 800; }
.stat-red .stat-icon { background: #ffe8ea; color: var(--red); }
.stat-label { color: #273d60; font-size: 16px; font-weight: 800; white-space: nowrap; }
.stat-blue .stat-label { color: var(--blue); }
.stat-red .stat-label { color: var(--red); }
.stat-value { margin-bottom: 20px; color: var(--blue); font-size: 60px; font-weight: 800; line-height: 1; }
.stat-red .stat-value { color: var(--red); }
.sparkline { position: absolute; left: 18px; right: 18px; bottom: 10px; height: 18px; opacity: 0.95; color: var(--blue); background: linear-gradient(135deg, transparent 0 10%, currentColor 10% 12%, transparent 12% 24%, currentColor 24% 26%, transparent 26% 39%, currentColor 39% 42%, transparent 42% 56%, currentColor 56% 58%, transparent 58% 69%, currentColor 69% 72%, transparent 72% 84%, currentColor 84% 86%, transparent 86% 100%); }
.stat-red .sparkline { color: var(--red); }

.list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.item { display: grid; grid-template-columns: 140px minmax(0, 1fr) 22px; align-items: center; gap: 18px; padding: 10px; border: 1px solid #e0ebf8; border-radius: 12px; background: rgba(255, 255, 255, 0.82); box-shadow: 0 6px 16px rgba(35, 88, 155, 0.06); cursor: pointer; transition: 0.2s; }
.item:hover { border-color: #bfd8ff; transform: translateY(-1px); box-shadow: 0 10px 22px rgba(35, 88, 155, 0.12); }
.img-box { position: relative; width: 140px; height: 72px; border-radius: 8px; overflow: hidden; background: #edf5ff; }
.img-box img { width: 100%; height: 100%; object-fit: contain; }
.img-box .time { position: absolute; right: 6px; bottom: 4px; padding: 2px 5px; background: rgba(0,0,0,0.58); color: #fff; font-size: 12px; font-weight: 700; border-radius: 4px; }
.body { min-width: 0; }
.row { color: #304462; font-size: 15px; font-weight: 600; line-height: 1.7; }
.row strong { color: var(--red); font-weight: 800; }
.body p { font-size: 13px; color: #7185a5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.arrow { color: #416896; font-size: 28px; opacity: 0.5; font-weight: 300; }

.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 200px; border: 1px dashed #bfd4ef; border-radius: 12px; color: #7486a3; }
.e-icon { font-size: 40px; margin-bottom: 12px; opacity: 0.4; }

.detail-main { display: flex; gap: 25px; margin-bottom: 25px; }
.detail-img { width: 450px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.detail-info p { margin-bottom: 12px; font-size: 16px; color: #334155; }
.detail-raw h4 { margin-bottom: 12px; color: #0c234d; }
.detail-raw pre { background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; font-size: 13px; white-space: pre-wrap; word-break: break-all; color: #64748b; }
.frame-detail { background: #111; border-radius: 12px; overflow: hidden; }
.frame-viewport { position: relative; width: 100%; }
.frame-img { width: 100%; height: 100%; object-fit: contain; display: block; }
.frame-rect { z-index: 2; }
.modal-list { max-height: 620px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.reminder-empty { min-height: 260px; }
</style>
