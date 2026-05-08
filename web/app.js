import { createApp, ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { Button, Modal, Spin, Tag, message } from "./antd.esm.js";

const API_BASE = window.MONITOR_API_BASE || "http://127.0.0.1:8001";

const App = {
  setup() {
    const loading = ref(true);
    const starting = ref(false);
    const status = ref(null);
    const curEvent = ref(null);
    const showDetail = ref(false);
    const showSeatMap = ref(false);
    const loadingDetail = ref(false);
    const timer = ref(null);
    const video = ref(null);
    const playing = ref(false);
    const volume = ref(0);
    const videoProgress = ref(0);

    const apiUrl = (path) => `${API_BASE}${path}`;
    const mediaUrl = (path) => `${API_BASE}${path}`;

    const requestJson = async (path, options = {}) => {
      const response = await fetch(apiUrl(path), {
        headers: { "Content-Type": "application/json" },
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
      if (!status.value) return "-";
      if (status.value.phase === "init") return "正在建立座位图";
      if (status.value.phase === "monitor") return "正在监控";
      if (status.value.phase === "done") return "监控完成";
      if (status.value.phase === "error") return "运行失败";
      return "待启动";
    });

    const phaseClass = computed(() => {
      if (!status.value) return "tone-blue";
      if (status.value.phase === "error") return "tone-red";
      if (status.value.phase === "monitor") return "tone-cyan";
      if (status.value.phase === "init") return "tone-gold";
      return "tone-blue";
    });

    const remindColor = (level) => (level === "FOCUS" ? "red" : "blue");
    const levelColor = (level) => {
      if (level === "STRONG") return "red";
      if (level === "WEAK") return "gold";
      if (level === "NORMAL") return "green";
      return "default";
    };

    const statusText = (value) => {
      if (value === "STRONG") return "明显异常";
      if (value === "WEAK") return "轻度异常";
      if (value === "NORMAL") return "正常";
      if (value === "EMPTY") return "空位";
      if (value === "INVALID") return "关键点不足";
      return value || "-";
    };

    const formatRatio = (value) => {
      if (value === null || value === undefined) return "-";
      return Number(value).toFixed(4);
    };

    const refreshStatus = async () => {
      try {
        status.value = await requestJson("/api/monitor/status");
        if (status.value?.error) {
          message.error(status.value.error);
        }
      } catch (error) {
        message.error(error.message || "状态加载失败");
      } finally {
        loading.value = false;
      }
    };

    const refreshDetail = async (eventId) => {
      loadingDetail.value = true;
      try {
        curEvent.value = await requestJson(`/api/events/${eventId}`);
      } finally {
        loadingDetail.value = false;
      }
    };

    const startPolling = () => {
      if (timer.value) clearInterval(timer.value);
      timer.value = setInterval(refreshStatus, 2000);
    };

    const startMonitor = async () => {
      starting.value = true;
      try {
        const result = await requestJson("/api/monitor/start", { method: "POST" });
        message.success(result.message || "监控已启动");
        await refreshStatus();
        await nextTick();
        if (video.value) {
          video.value.currentTime = 0;
          await video.value.play().catch(() => {});
          playing.value = !video.value.paused;
        }
      } catch (error) {
        message.error(error.message || "启动失败");
      } finally {
        starting.value = false;
      }
    };

    const syncVideoState = () => {
      if (!video.value) return;
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
      if (!video.value) return;
      if (video.value.paused) {
        await video.value.play().catch(() => {});
      } else {
        video.value.pause();
      }
      syncVideoState();
    };

    const updateVolume = (e) => {
      if (!video.value) return;
      const next = Number(e.target.value) / 100;
      video.value.volume = next;
      video.value.muted = next <= 0;
      syncVideoState();
    };

    const seekVideo = (e) => {
      if (!video.value || !Number.isFinite(video.value.duration) || video.value.duration <= 0) return;
      video.value.currentTime = (Number(e.target.value) / 100) * video.value.duration;
      updateVideoProgress();
    };

    const openEvent = async (eventId) => {
      try {
        showDetail.value = true;
        curEvent.value = null;
        await refreshDetail(eventId);
      } catch (error) {
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
      await refreshStatus();
      startPolling();
    });

    onBeforeUnmount(() => {
      if (timer.value) clearInterval(timer.value);
    });

    return {
      loading,
      starting,
      status,
      curEvent,
      showDetail,
      showSeatMap,
      loadingDetail,
      events,
      focusCount,
      normalCount,
      phaseText,
      phaseClass,
      video,
      playing,
      volume,
      videoProgress,
      remindColor,
      levelColor,
      statusText,
      formatRatio,
      mediaUrl,
      refreshStatus,
      startMonitor,
      togglePlay,
      updateVolume,
      updateVideoProgress,
      seekVideo,
      syncVideoState,
      openEvent,
      openSeatMap,
    };
  },
  template: `
    <div class="screen">
      <header class="topbar">
        <div class="brand-lockup">
          <div class="brand-icon">
            <span class="brand-icon-camera"></span>
          </div>
          <div>
            <h1 class="brand-title">课堂异常行为监测系统</h1>
            <div class="brand-subtitle">AI 智能识别 · 实时预警 · 规范课堂秩序 · 提升教学质量</div>
          </div>
        </div>

        <div class="top-actions">
          <span class="brand-status" :class="phaseClass" v-if="status">{{ phaseText }}</span>
          <a-button @click="refreshStatus">刷新</a-button>
          <a-button type="primary" :loading="starting" @click="startMonitor">启动监控</a-button>
        </div>
      </header>

      <a-spin :spinning="loading">
        <template v-if="status">
          <main class="main-grid">
            <section class="panel stage-panel">
              <div class="panel-bar">
                <div>
                  <h2 class="panel-title"><span class="title-icon camera-icon"></span>主监控画面</h2>
                </div>
                <div class="panel-meta">
                  <span>{{ status.current_time }}</span>
                  <span class="online-dot"></span>
                  <span>在线</span>
                </div>
              </div>

              <div class="stage-box">
                <div class="live-badge"><span></span>LIVE</div>
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
                    {{ playing ? 'Ⅱ' : '▶' }}
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
                  <h2 class="panel-title"><span class="title-icon pulse-icon"></span>实时统计</h2>
                  <span class="panel-link">今日数据</span>
                </div>
                <div class="stats-grid">
                  <div class="stat-card stat-blue stat-clickable" @click="openSeatMap">
                    <div class="stat-head">
                      <div class="stat-icon">♙</div>
                      <div class="stat-label">座位数量</div>
                    </div>
                    <div class="stat-value">{{ status.seat_count }}</div>
                    <div class="sparkline"></div>
                  </div>
                  <div class="stat-card stat-red">
                    <div class="stat-head">
                      <div class="stat-icon">!</div>
                      <div class="stat-label">重点提醒</div>
                    </div>
                    <div class="stat-value">{{ focusCount }}</div>
                    <div class="sparkline"></div>
                  </div>
                  <div class="stat-card stat-blue">
                    <div class="stat-head">
                      <div class="stat-icon">●</div>
                      <div class="stat-label">普通提醒</div>
                    </div>
                    <div class="stat-value">{{ normalCount }}</div>
                    <div class="sparkline"></div>
                  </div>
                </div>
              </section>

              <section class="panel alert-panel">
                <div class="panel-bar panel-bar-side">
                  <h2 class="panel-title"><span class="title-icon shield-icon"></span>异常行为通知</h2>
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
                      <span class="thumb-time">{{ item.alert_start_time || item.start_time }}</span>
                    </div>

                    <div class="alert-body">
                      <div class="alert-seat">学生座位：{{ item.seat_name }}</div>
                      <div class="alert-action">异常行为：<strong>{{ item.level === 'STRONG' ? '趴桌' : '低头' }}</strong></div>
                    </div>

                    <a-tag class="alert-level" :color="remindColor(item.reminder_level)">{{ item.reminder_text }}</a-tag>
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
          <img class="seat-map-image" :src="mediaUrl(status.seat_map_url)" alt="seat-map" />
        </div>
        <div v-else class="empty-state">座位图还未生成</div>
      </a-modal>
    </div>
  `,
};

const app = createApp(App);
app.use(Button);
app.use(Modal);
app.use(Spin);
app.use(Tag);
app.mount("#app");
