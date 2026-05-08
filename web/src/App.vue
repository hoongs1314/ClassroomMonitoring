<script setup>

const API_BASE = window.MONITOR_API_BASE || "http://127.0.0.1:8001";
import {ref, computed, onMounted, onBeforeUnmount, nextTick} from "vue";
import {message} from "ant-design-vue"
import {
  AlertOutlined,
  BellOutlined,
  CheckCircleFilled,
  DashboardOutlined,
  PauseOutlined,
  PlayCircleFilled,
  DesktopOutlined,
  SafetyCertificateOutlined,
  BulbOutlined,
  TeamOutlined,
  VideoCameraFilled,
  VideoCameraOutlined,
} from "@ant-design/icons-vue";

const loading = ref(true);
const starting = ref(false);
const monitorStarted = ref(false);
const status = ref(null);
const curEvent = ref(null);
const showDetail = ref(false);
const showSeatMap = ref(false);
const loadingDetail = ref(false);
const socket = ref(null);
const video = ref(null);
const playing = ref(false);
const volume = ref(0);
const videoProgress = ref(0);

const apiUrl = (path) => `${API_BASE}${path}`;
const wsUrl = (path) => `${API_BASE.replace(/^http/, "ws")}${path}`;
const mediaUrl = (path) => `${API_BASE}${path}`;

const requestJson = async (path, options = {}) => {
  const response = await fetch(apiUrl(path), {
    headers: {"Content-Type": "application/json"},
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || "请求失败");
  }
  return data;
};

const events = computed(() => status.value?.events || []);
const focusCount = computed(() => events.value.filter((item) => item.reminder_level === "FOCUS").length);
const normalCount = computed(() => events.value.filter((item) => item.reminder_level !== "FOCUS").length);

const phaseText = computed(() => {
  if (!status.value) {
    return "-";
  }
  if (status.value.phase === "init") {
    return "正在建立座位图";
  }
  if (status.value.phase === "monitor") {
    return "正在监控";
  }
  if (status.value.phase === "done") {
    return "监控完成";
  }
  if (status.value.phase === "error") {
    return "运行失败";
  }
  return "待启动";
});

const phaseClass = computed(() => {
  if (!status.value) {
    return "tone-blue";
  }
  if (status.value.phase === "error") {
    return "tone-red";
  }
  if (status.value.phase === "monitor") {
    return "tone-cyan";
  }
  if (status.value.phase === "init") {
    return "tone-gold";
  }
  return "tone-blue";
});

const remindColor = (level) => (level === "FOCUS" ? "red" : "blue");
const levelColor = (level) => {
  if (level === "STRONG") {
    return "red";
  }
  if (level === "WEAK") {
    return "gold";
  }
  if (level === "NORMAL") {
    return "green";
  }
  return "default";
};

const statusText = (value) => {
  if (value === "STRONG") {
    return "明显异常";
  }
  if (value === "WEAK") {
    return "轻度异常";
  }
  if (value === "NORMAL") {
    return "正常";
  }
  if (value === "EMPTY") {
    return "空位";
  }
  if (value === "INVALID") {
    return "关键点不足";
  }
  return value || "-";
};

const formatRatio = (value) => {
  if (value === null || value === undefined) {
    return "-";
  }
  return Number(value).toFixed(4);
};

const refreshDetail = async (eventId) => {
  loadingDetail.value = true;
  try {
    curEvent.value = await requestJson(`/api/events/${eventId}`);
  }
  finally {
    loadingDetail.value = false;
  }
};

const connectStatus = () => {
  if (socket.value) {
    socket.value.close();
  }
  const ws = new WebSocket(wsUrl("/ws/monitor"));
  socket.value = ws;

  ws.onmessage = (event) => {
    status.value = JSON.parse(event.data);
    loading.value = false;
    if (monitorStarted.value) {
      nextTick(() => {
        if (video.value && video.value.paused) {
          video.value.play().catch(() => {
          });
        }
      });
    }
    if (status.value?.error) {
      message.error(status.value.error);
    }
  };
  ws.onerror = () => {
    loading.value = false;
    message.error("状态连接失败");
  };
};

const resetVideo = () => {
  if (!video.value) {
    playing.value = false;
    videoProgress.value = 0;
    volume.value = 0;
    return;
  }
  video.value.pause();
  video.value.currentTime = 0;
  video.value.muted = true;
  video.value.volume = 0;
  syncVideoState();
  videoProgress.value = 0;
};

const resetPage = () => {
  if (socket.value) {
    socket.value.close();
    socket.value = null;
  }
  resetVideo();
  monitorStarted.value = false;
  status.value = null;
  curEvent.value = null;
  showDetail.value = false;
  showSeatMap.value = false;
  loadingDetail.value = false;
  loading.value = false;
};

const startMonitor = async () => {
  starting.value = true;
  try {
    if (!socket.value || socket.value.readyState === WebSocket.CLOSED) {
      connectStatus();
    }
    const result = await requestJson("/api/monitor/start", {method: "POST"});
    monitorStarted.value = true;
    message.success(result.message || "监控已启动");
    await nextTick();
    if (video.value) {
      video.value.currentTime = 0;
      await video.value.play().catch(() => {
      });
      playing.value = !video.value.paused;
    }
  }
  catch (error) {
    message.error(error.message || "启动失败");
  }
  finally {
    starting.value = false;
  }
};

const stopMonitor = () => {
  resetVideo();
  monitorStarted.value = false;
};

const syncVideoState = () => {
  if (!video.value) {
    return;
  }
  playing.value = !video.value.paused;
  volume.value = Math.round((video.value.muted ? 0 : video.value.volume) * 100);
  updateVideoProgress();
};

const updateVideoProgress = () => {
  if (!video.value || !Number.isFinite(video.value.duration) || video.value.duration <= 0) {
    videoProgress.value = 0;
    return;
  }
  videoProgress.value = (video.value.currentTime / video.value.duration) * 100;
};

const togglePlay = async () => {
  if (!video.value) {
    return;
  }
  if (video.value.paused) {
    await video.value.play().catch(() => {
    });
  }
  else {
    video.value.pause();
  }
  syncVideoState();
};

const updateVolume = (e) => {
  if (!video.value) {
    return;
  }
  const next = Number(e.target.value) / 100;
  video.value.volume = next;
  video.value.muted = next <= 0;
  syncVideoState();
};

const seekVideo = (e) => {
  if (!video.value || !Number.isFinite(video.value.duration) || video.value.duration <= 0) {
    return;
  }
  video.value.currentTime = (Number(e.target.value) / 100) * video.value.duration;
  updateVideoProgress();
};

const openEvent = async (eventId) => {
  try {
    showDetail.value = true;
    curEvent.value = null;
    await refreshDetail(eventId);
  }
  catch (error) {
    showDetail.value = false;
    message.error(error.message || "详情加载失败");
  }
};

const openSeatMap = () => {
  if (!status.value?.seat_map_url) {
    message.info("座位图还未生成，请先启动监控并等待座位识别完成");
    return;
  }
  showSeatMap.value = true;
};

onMounted(async () => {
  connectStatus();
});

onBeforeUnmount(() => {
  if (socket.value) {
    socket.value.close();
  }
});

</script>

<template>
  <a-config-provider prefix-cls="ant" icon-prefix-cls="anticon">
    <div class="screen">
      <header class="topbar">
        <div class="brand-lockup">
          <div class="brand-icon">
            <VideoCameraFilled/>
          </div>
          <div>
            <h1 class="brand-title">课堂异常行为监测系统</h1>
            <div class="brand-subtitle">AI 智能识别 · 实时预警 · 规范课堂秩序 · 提升教学质量</div>
          </div>
        </div>

        <div class="top-actions">
          <span class="brand-status" :class="phaseClass" v-if="monitorStarted && status">{{ phaseText }}</span>
          <a-button @click="resetPage">重置</a-button>
          <a-button v-if="!monitorStarted" type="primary" :loading="starting" @click="startMonitor">启动监控</a-button>
          <a-button v-else danger @click="stopMonitor">停止监控</a-button>
        </div>
      </header>

      <a-spin :spinning="loading">
        <template v-if="status">
          <main class="main-grid">
            <section class="panel stage-panel">
              <div class="panel-bar">
                <div>
                  <h2 class="panel-title"><span class="title-icon"><DesktopOutlined /></span>主监控画面</h2>
                </div>
                <div class="panel-meta">
                  <span>{{ status.current_time }}</span>
                  <CheckCircleFilled class="online-icon"/>
                  <span>在线</span>
                </div>
              </div>

              <div class="stage-box">
                <div class="live-badge">
                  <VideoCameraFilled class="live-icon"/>
                  LIVE
                </div>
                <video
                    ref="video"
                    v-if="status.video_url"
                    :src="mediaUrl(status.video_url)"
                    muted
                    playsinline
                    @play="syncVideoState"
                    @pause="syncVideoState"
                    @volumechange="syncVideoState"
                    @loadedmetadata="syncVideoState"
                    @timeupdate="updateVideoProgress"
                ></video>

                <div class="video-controls">
                  <button type="button" class="control-icon" :title="playing ? '暂停' : '播放'" @click="togglePlay">
                    <PauseOutlined v-if="playing"/>
                    <PlayCircleFilled v-else/>
                  </button>
                  <input
                      class="progress-range"
                      type="range"
                      min="0"
                      max="100"
                      step="0.1"
                      :value="videoProgress"
                      title="播放进度"
                      @input="seekVideo"
                  />
                  <input
                      class="volume-range"
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      :value="volume"
                      title="声音大小"
                      @input="updateVolume"
                  />
                </div>
              </div>
            </section>

            <aside class="side-rail">
              <section class="panel stats-panel">
                <div class="panel-bar">
                  <h2 class="panel-title"><span class="title-icon"><DashboardOutlined/></span>实时统计</h2>
                  <span class="panel-link">今日数据</span>
                </div>
                <div class="stats-grid">
                  <div class="stat-card stat-blue stat-clickable" @click="openSeatMap">
                    <div class="stat-head">
                      <div class="stat-icon">
                        <TeamOutlined/>
                      </div>
                      <div class="stat-label">座位数量</div>
                    </div>
                    <div class="stat-value">{{ status.seat_count }}</div>
                    <div class="sparkline"></div>
                  </div>
                  <div class="stat-card stat-red">
                    <div class="stat-head">
                      <div class="stat-icon">
                        <AlertOutlined/>
                      </div>
                      <div class="stat-label">重点提醒</div>
                    </div>
                    <div class="stat-value">{{ focusCount }}</div>
                    <div class="sparkline"></div>
                  </div>
                  <div class="stat-card stat-green">
                    <div class="stat-head">
                      <div class="stat-icon">
                        <BellOutlined/>
                      </div>
                      <div class="stat-label">普通提醒</div>
                    </div>
                    <div class="stat-value">{{ normalCount }}</div>
                    <div class="sparkline"></div>
                  </div>
                </div>
              </section>

              <section class="panel alert-panel">
                <div class="panel-bar panel-bar-side">
                  <h2 class="panel-title"><span class="title-icon"><BulbOutlined /></span>异常行为通知</h2>
                  <span class="panel-link">查看全部</span>
                </div>

                <div v-if="events.length" class="alert-list">
                  <article
                      v-for="item in events"
                      :key="item.event_id"
                      class="alert-card"
                      :class="{ active: curEvent && curEvent.event_id === item.event_id }"
                      @click="openEvent(item.event_id)"
                  >
                    <div v-if="item.list_image_url" class="image-stage">
                      <img
                          class="alert-thumb"
                          :src="mediaUrl(item.list_image_url)"
                          :alt="item.list_title"
                      />
                      <span class="thumb-time">{{ item.alert_start_time }}</span>
                    </div>

                    <div class="alert-body">
                      <div class="alert-seat">学生座位：{{ item.seat_name }}</div>
                      <div class="alert-action">异常行为：<strong>{{
                          item.level === 'STRONG' ? '趴桌' : '低头'
                        }}</strong></div>
                    </div>

                    <a-tag class="alert-level" :color="remindColor(item.reminder_level)">{{
                        item.reminder_text
                      }}
                    </a-tag>
                    <span class="alert-arrow">›</span>
                  </article>
                </div>

                <div v-else class="empty-state">当前没有异常事件</div>
              </section>
            </aside>
          </main>
        </template>
      </a-spin>

      <a-modal
          v-model:open="showDetail"
          :footer="null"
          width="1180px"
          centered
          destroyOnClose
          wrap-class-name="detail-modal"
      >
        <template #title>
          <span v-if="curEvent">{{ curEvent.list_title }}</span>
          <span v-else>异常详情</span>
        </template>

        <div v-if="loadingDetail" class="detail-loading">
          <div class="detail-loading-panel"></div>
        </div>

        <template v-else-if="curEvent">
          <div class="detail-shell">
            <div class="detail-top">
              <div>
                <h3 class="detail-seat">{{ curEvent.seat_name }}</h3>
                <div class="detail-summary">{{ curEvent.summary_text }}</div>
              </div>
              <a-tag :color="remindColor(curEvent.reminder_level)">{{ curEvent.reminder_text }}</a-tag>
            </div>

            <div class="detail-cards">
              <div class="detail-info-card">
                <div class="detail-info-label">座位号</div>
                <div class="detail-info-value">{{ curEvent.seat_name }}</div>
              </div>
              <div class="detail-info-card">
                <div class="detail-info-label">开始时间</div>
                <div class="detail-info-value">{{ curEvent.alert_start_time || curEvent.start_time }}</div>
              </div>
              <div class="detail-info-card">
                <div class="detail-info-label">结束时间</div>
                <div class="detail-info-value">{{ curEvent.end_time }}</div>
              </div>
              <div class="detail-info-card">
                <div class="detail-info-label">持续秒数</div>
                <div class="detail-info-value">{{ curEvent.duration_seconds }}</div>
              </div>
              <div class="detail-info-card">
                <div class="detail-info-label">峰值比例</div>
                <div class="detail-info-value">{{ formatRatio(curEvent.peak_ratio) }}</div>
              </div>
            </div>

            <div class="frame-list">
              <article
                  v-for="frame in (curEvent.frames || [])"
                  :key="frame.frame_index + '-' + frame.seat.seat_id"
                  class="frame-item"
              >
                <div v-if="frame.focus_image_url" class="image-stage image-stage-detail">
                  <img
                      class="frame-thumb"
                      :src="mediaUrl(frame.focus_image_url)"
                      alt="seat-focus"
                  />
                </div>

                <div class="frame-content">
                  <div class="frame-top">
                    <strong>第 {{ frame.frame_index }} 帧</strong>
                    <a-tag :color="levelColor(frame.seat.status)">
                      {{ frame.seat.status_text || statusText(frame.seat.status) }}
                    </a-tag>
                  </div>
                  <div class="frame-meta">
                    <div><b>时间:</b> {{ frame.time }}</div>
                    <div><b>座位:</b> {{ frame.seat.seat_name }}</div>
                    <div><b>比例:</b> {{ formatRatio(frame.seat.ratio) }}</div>
                    <div><b>置信度:</b> {{ frame.seat.box_conf ?? '-' }}</div>
                  </div>
                </div>
              </article>

              <div v-if="!curEvent.frames || !curEvent.frames.length" class="empty-state">
                当前事件没有可用明细
              </div>
            </div>
          </div>
        </template>

        <div v-else class="empty-state">当前事件详情暂时不可用</div>
      </a-modal>

      <a-modal
          v-model:open="showSeatMap"
          :footer="null"
          width="1180px"
          centered
          destroyOnClose
          wrap-class-name="detail-modal"
      >
        <template #title>
          <span>座位识别图</span>
        </template>

        <div class="seat-map-shell" v-if="status && status.seat_map_url">
          <img class="seat-map-image" :src="mediaUrl(status.seat_map_url)" alt="seat-map"/>
        </div>
        <div v-else class="empty-state">座位图还未生成</div>
      </a-modal>
    </div>
  </a-config-provider>
</template>

<style scoped>
:global(:root) {
  --bg: #eef6ff;
  --panel: rgba(255, 255, 255, 0.92);
  --panel-solid: #ffffff;
  --line: #dce9fa;
  --line-strong: #c6dcfa;
  --text: #10264b;
  --muted: #7185a5;
  --blue: #1268f3;
  --blue-soft: #e9f2ff;
  --red: #ff3f45;
  --red-soft: #fff0f1;
  --orange: #ff8a1f;
  --green: #16b45f;
  --shadow: 0 18px 42px rgba(35, 88, 155, 0.14);
  --shadow-soft: 0 8px 24px rgba(35, 88, 155, 0.10);
  --radius-xl: 18px;
  --radius-lg: 14px;
  --radius-md: 10px;
}

* {
  box-sizing: border-box;
}

:global(html),
:global(body) {
  height: 100%;
  margin: 0;
  overflow: hidden;
}

:global(body) {
  color: var(--text);
  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;
  background: linear-gradient(135deg, rgba(218, 236, 255, 0.9), rgba(248, 252, 255, 0.7)),
  radial-gradient(circle at 15% 8%, rgba(18, 104, 243, 0.11), transparent 32%),
  #f4f9ff;
}

.screen {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  padding: 12px 22px;
}

.screen > .ant-spin-nested-loading,
.screen > .ant-spin-nested-loading > .ant-spin-container {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
}

.topbar {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  min-height: 96px;
  padding: 18px 28px;
  margin-bottom: 12px;
  overflow: hidden;
  border: 1px solid rgba(191, 216, 249, 0.76);
  border-radius: var(--radius-xl);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(247, 251, 255, 0.94)),
  repeating-linear-gradient(
      0deg,
      rgba(18, 104, 243, 0.03) 0,
      rgba(18, 104, 243, 0.03) 1px,
      transparent 1px,
      transparent 7px
  );
  box-shadow: var(--shadow-soft);
}

.topbar::after {
  content: "";
  position: absolute;
  right: 44px;
  top: 14px;
  width: 360px;
  height: 88px;
  opacity: 0.42;
  background: radial-gradient(circle at 86% 50%, rgba(18, 104, 243, 0.20), transparent 16%),
  repeating-radial-gradient(ellipse at 100% 50%, transparent 0 17px, rgba(18, 104, 243, 0.16) 18px 19px);
  pointer-events: none;
}

.brand-lockup {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 22px;
  min-width: 0;
}


.brand-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 20px;
  width: 50px;
  height: 50px;
  flex: 0 0 auto;
  border-radius: 10px;
  background: linear-gradient(180deg, #0d6dff, #0758e8);
  box-shadow: 0 10px 20px rgba(18, 104, 243, 0.24);
}

.brand-title {
  margin: 0;
  color: #0c234d;
  font-size: 30px;
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: 0;
}

.brand-subtitle {
  margin-top: 8px;
  color: #7083a2;
  font-size: 15px;
  font-weight: 500;
}

.top-actions {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.brand-status {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 13px;
  border-radius: 999px;
  border: 1px solid #cfe1fa;
  background: #f2f7ff;
  color: #31547f;
  font-size: 13px;
  font-weight: 700;
}

.brand-status.tone-cyan {
  border-color: rgba(22, 180, 95, 0.22);
  background: #eefcf5;
  color: #14834b;
}

.brand-status.tone-gold {
  border-color: rgba(255, 138, 31, 0.25);
  background: #fff6ea;
  color: #a15a09;
}

.brand-status.tone-red {
  border-color: rgba(255, 63, 69, 0.24);
  background: #fff0f1;
  color: #c72830;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(420px, 0.98fr);
  gap: 20px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.side-rail {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 16px;
  min-height: 0;
}

.panel {
  border: 1px solid rgba(210, 226, 248, 0.92);
  border-radius: var(--radius-xl);
  background: var(--panel);
  box-shadow: var(--shadow);
}

.stage-panel,
.stats-panel,
.alert-panel {
  padding: 18px;
}

.stage-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  color: #045be6;
  font-size: 22px;
  font-weight: 800;
  line-height: 1.25;
}

.title-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--blue-soft);
  color: var(--blue);
}

.camera-icon::before {
  content: "";
  width: 17px;
  height: 13px;
  border-radius: 4px;
  background: currentColor;
}

.camera-icon::after {
  content: "";
  position: absolute;
  right: 8px;
  width: 5px;
  height: 7px;
  border-radius: 2px;
  background: currentColor;
}

.pulse-icon::before {
  content: "";
  width: 20px;
  height: 12px;
  border-left: 3px solid currentColor;
  border-bottom: 3px solid currentColor;
  transform: skewX(-24deg);
}

.shield-icon::before {
  content: "";
  width: 16px;
  height: 19px;
  border-radius: 8px 8px 10px 10px;
  background: currentColor;
  clip-path: polygon(50% 0, 92% 18%, 82% 78%, 50% 100%, 18% 78%, 8% 18%);
}

.panel-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  color: #617592;
  font-size: 15px;
  font-weight: 500;
  white-space: nowrap;
}

.online-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #16b45f;
  box-shadow: 0 0 0 4px rgba(22, 180, 95, 0.12);
}

.panel-link {
  color: #6d7f9c;
  font-size: 14px;
  font-weight: 700;
  white-space: nowrap;
}

.stage-box {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-radius: 15px;
  background: #111;
  box-shadow: 0 16px 32px rgba(31, 67, 115, 0.16);
}

.stage-box video {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 0;
  object-fit: cover;
  background: #0b0f15;
}

.live-badge {
  position: absolute;
  z-index: 3;
  left: 22px;
  top: 18px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 15px;
  border-radius: 9px;
  background: #ff333d;
  color: #fff;
  font-size: 16px;
  font-weight: 800;
  box-shadow: 0 10px 18px rgba(255, 51, 61, 0.28);
}

.live-badge span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
}

.video-controls {
  position: absolute;
  z-index: 4;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 18px;
  height: 64px;
  padding: 0 28px;
  background: linear-gradient(180deg, rgba(6, 10, 16, 0.12), rgba(6, 10, 16, 0.88));
}

.control-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  cursor: pointer;
}

.control-icon:hover {
  background: rgba(255, 255, 255, 0.14);
}

.progress-range {
  flex: 1;
  min-width: 120px;
  height: 4px;
  accent-color: #1677ff;
}

.volume-range {
  width: 150px;
  height: 4px;
  accent-color: #1677ff;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  position: relative;
  min-height: 140px;
  overflow: hidden;
  padding: 16px 16px 14px;
  border: 1px solid #b9d6ff;
  border-radius: 12px;
  background:
      radial-gradient(circle at 100% 0, rgba(18, 104, 243, 0.18), transparent 34%),
      linear-gradient(180deg, #f8fbff, #edf5ff);
  box-shadow: 0 10px 24px rgba(18, 104, 243, 0.10);
}

.stat-clickable {
  cursor: pointer;
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}

.stat-clickable:hover {
  transform: translateY(-1px);
  border-color: #9bc4ff;
  box-shadow: 0 10px 22px rgba(35, 88, 155, 0.14);
}

.stat-red {
  border-color: #ffd3d6;
  background:
      radial-gradient(circle at 100% 0, rgba(255, 63, 69, 0.18), transparent 34%),
      linear-gradient(180deg, #fff8f8, #fff1f2);
  box-shadow: 0 10px 24px rgba(255, 63, 69, 0.10);
}

.stat-green {
  border-color: #bcebd2;
  background:
      radial-gradient(circle at 100% 0, rgba(22, 180, 95, 0.18), transparent 34%),
      linear-gradient(180deg, #f8fffb, #eefcf5);
  box-shadow: 0 10px 24px rgba(22, 180, 95, 0.10);
}

.stat-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 38px;
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #e7f1ff;
  color: var(--blue);
  font-size: 23px;
  font-weight: 800;
}

.stat-icon .anticon {
  color: currentColor;
  font-size: 23px;
}

.stat-red .stat-icon {
  background: #ffe8ea;
  color: var(--red);
}

.stat-green .stat-icon {
  background: #dff8eb;
  color: var(--green);
}

.stat-label {
  color: #273d60;
  font-size: 16px;
  font-weight: 800;
  white-space: nowrap;
}

.stat-value {
  margin-bottom: 20px;
  color: var(--blue);
  font-size: 60px;
  font-weight: 800;
  line-height: 1;
}

.stat-red .stat-value {
  color: var(--red);
}

.stat-green .stat-value {
  color: var(--green);
}

.sparkline {
  position: absolute;
  left: 18px;
  right: 18px;
  bottom: 10px;
  height: 18px;
  opacity: 0.95;
  background: linear-gradient(135deg, transparent 0 10%, currentColor 10% 12%, transparent 12% 24%, currentColor 24% 26%, transparent 26% 39%, currentColor 39% 42%, transparent 42% 56%, currentColor 56% 58%, transparent 58% 69%, currentColor 69% 72%, transparent 72% 84%, currentColor 84% 86%, transparent 86% 100%);
  color: var(--blue);
}

.stat-red .sparkline {
  color: var(--red);
}

.stat-green .sparkline {
  color: var(--green);
}

.alert-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  flex: 1;
  padding-right: 2px;
  overflow-y: auto;
  max-height: 50vh;
}

.alert-card {
  position: relative;
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) auto 22px;
  align-items: center;
  gap: 18px;
  min-height: 92px;
  padding: 10px 14px 10px 10px;
  border: 1px solid #e0ebf8;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 6px 16px rgba(35, 88, 155, 0.06);
  cursor: pointer;
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}

.alert-card:hover,
.alert-card.active {
  transform: translateY(-1px);
  border-color: #bfd8ff;
  box-shadow: 0 10px 22px rgba(35, 88, 155, 0.12);
}

.image-stage {
  position: relative;
  width: 140px;
  height: 72px;
  overflow: hidden;
  border-radius: 8px;
  background: #edf5ff;
}

.alert-thumb {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.thumb-time {
  position: absolute;
  right: 6px;
  bottom: 4px;
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.58);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.alert-body {
  min-width: 0;
}

.alert-seat,
.alert-action {
  color: #304462;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.7;
}

.alert-action strong {
  color: var(--red);
  font-weight: 800;
}

.alert-arrow {
  color: #416896;
  font-size: 28px;
  font-weight: 300;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 150px;
  padding: 24px;
  border: 1px dashed #bfd4ef;
  border-radius: 12px;
  color: #7486a3;
  background: rgba(248, 251, 255, 0.78);
  text-align: center;
}

.detail-modal .ant-modal-content {
  overflow: hidden;
  border-radius: 18px;
  background: #f8fbff;
  box-shadow: 0 24px 70px rgba(35, 88, 155, 0.22);
}

.detail-modal .ant-modal-header {
  padding: 18px 24px 14px;
  background: #fff;
  border-bottom: 1px solid #e2edf9;
}

.detail-modal .ant-modal-title,
.detail-modal .ant-modal-close,
.detail-modal .ant-modal-close-x {
  color: var(--text);
}

.detail-modal .ant-modal-body {
  padding: 16px 20px 20px;
  color: var(--text);
}

.detail-loading {
  min-height: 420px;
  display: flex;
}

.detail-loading-panel {
  width: 100%;
  min-height: 420px;
  border-radius: 16px;
  background: linear-gradient(90deg, #eef5ff 25%, #ffffff 50%, #eef5ff 75%);
  background-size: 220% 100%;
  animation: screen-shine 1.2s ease-in-out infinite;
}

.detail-shell {
  max-height: 76vh;
  overflow: auto;
}

.detail-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.detail-seat {
  margin: 0;
  color: #112a56;
  font-size: 24px;
  font-weight: 800;
}

.detail-summary {
  margin-top: 8px;
  color: #617592;
  font-size: 14px;
  line-height: 1.7;
}

.detail-cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.detail-info-card {
  padding: 14px;
  border: 1px solid #dce9fa;
  border-radius: 12px;
  background: #fff;
}

.detail-info-label {
  color: #7185a5;
  font-size: 12px;
}

.detail-info-value {
  margin-top: 8px;
  color: #10264b;
  font-size: 17px;
  font-weight: 800;
}

.frame-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 20px;
}

.frame-item {
  overflow: hidden;
  border: 1px solid #dce9fa;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 10px 22px rgba(35, 88, 155, 0.08);
}

.image-stage-detail {
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 10;
  border-radius: 0;
}

.frame-thumb {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #edf5ff;
}

.seat-map-shell {
  width: 100%;
  max-height: 78vh;
  overflow: auto;
  border: 1px solid #dce9fa;
  border-radius: 14px;
  background: #edf5ff;
}

.seat-map-image {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
}

.frame-content {
  padding: 9px 10px 10px;
}

.frame-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.frame-top strong {
  font-size: 13px;
}

.frame-meta {
  display: grid;
  gap: 3px;
  margin-top: 6px;
  color: #617592;
  font-size: 12px;
  line-height: 1.35;
}

.frame-meta b {
  color: #304462;
  font-weight: 700;
}

@keyframes screen-shine {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (max-width: 980px) {
  .main-grid {
    grid-template-columns: 1fr;
  }

  .stage-panel {
    min-height: auto;
  }

  .alert-list {
    max-height: 560px;
  }
}

@media (max-width: 820px) {
  .screen {
    padding: 12px;
  }

  .topbar,
  .brand-lockup,
  .top-actions,
  .panel-bar,
  .detail-top {
    align-items: flex-start;
    flex-direction: column;
  }

  .topbar {
    padding: 20px;
  }

  .brand-title {
    font-size: 26px;
  }

  .brand-subtitle {
    font-size: 13px;
    line-height: 1.7;
  }

  .stage-panel,
  .stats-panel,
  .alert-panel {
    padding: 16px;
  }

  .stats-grid,
  .detail-cards,
  .frame-list {
    grid-template-columns: 1fr;
  }

  .video-controls {
    height: 54px;
    gap: 10px;
    padding: 0 12px;
  }

  .control-icon {
    width: 28px;
    height: 28px;
    font-size: 17px;
  }

  .volume-range {
    width: 96px;
  }

  .alert-card {
    grid-template-columns: 108px minmax(0, 1fr) auto;
    gap: 12px;
  }

  .image-stage {
    width: 108px;
    height: 64px;
  }

  .alert-arrow {
    display: none;
  }
}

</style>
