import { createApp, ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";

import {
  Button,
  message,
  Modal,
  Spin,
  Tag} from './antd.esm.js'

const API_BASE = window.MONITOR_API_BASE || "http://127.0.0.1:8001";

const App = {
  setup() {
    const loading = ref(true);
    const starting = ref(false);
    const status = ref(null);
    const curEvent = ref(null);
    const showDetail = ref(false);
    const loadingDetail = ref(false);
    const timer = ref(null);
    const video = ref(null);
    const playing = ref(false);
    const volume = ref(0);

    const levelColor = (level) => {
      if (level === "STRONG") return "red";
      if (level === "WEAK") return "gold";
      return "blue";
    };

    const reminderColor = (level) => {
      if (level === "FOCUS") return "red";
      return "blue";
    };

    const statusText = (status, fallback = "") => {
      if (status === "STRONG") return "明显异常";
      if (status === "WEAK") return "轻度异常";
      if (status === "NORMAL") return "正常";
      if (status === "INVALID") return "无效";
      return fallback || status;
    };

    const formatRatio = (value) => {
      if (value === null || value === undefined) return "-";
      return Number(value).toFixed(4);
    };

    const apiUrl = (path) => `${API_BASE}${path}`;
    const mediaUrl = (path) => `${API_BASE}${path}`;

    const requestJson = async (path, options = {}) => {
      const response = await fetch(apiUrl(path), {
        headers: { "Content-Type": "application/json" },
        ...options,
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || `请求失败：${path}`);
      }
      return payload;
    };

    const events = computed(() => status.value?.events || []);
    const focusEventCount = computed(() => events.value.filter((item) => item.reminder_level === "FOCUS").length);
    const normalEventCount = computed(() => events.value.filter((item) => item.reminder_level !== "FOCUS").length);

    const refreshSelectedEvent = async (eventId) => {
      loadingDetail.value = true;
      try {
        curEvent.value = await requestJson(`/api/events/${eventId}`);
      } finally {
        loadingDetail.value = false;
      }
    };

    const refreshStatus = async () => {
      try {
        status.value = await requestJson("/api/monitor/status");

        if (!status.value.events.length) {
          curEvent.value = null;
          showDetail.value = false;
          return;
        }
      } catch (error) {
        message.error(error.message || "状态加载失败");
      } finally {
        loading.value = false;
      }
    };

    const startPolling = () => {
      if (timer.value) {
        clearInterval(timer.value);
      }
      timer.value = setInterval(() => {
        refreshStatus();
      }, 2000);
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
        message.error(error.message || "启动监控失败");
      } finally {
        starting.value = false;
      }
    };

    const syncVideoState = () => {
      if (!video.value) {
        return;
      }
      playing.value = !video.value.paused;
      volume.value = Math.round((video.value.muted ? 0 : video.value.volume) * 100);
    };

    const toggleVideoPlayback = async () => {
      if (!video.value) {
        return;
      }

      if (video.value.paused) {
        await video.value.play().catch(() => {});
      } else {
        video.value.pause();
      }
      syncVideoState();
    };

    const updateVideoVolume = (e) => {
      if (!video.value) {
        return;
      }
      const nextVolume = Number(e.target.value) / 100;
      video.value.volume = nextVolume;
      video.value.muted = nextVolume <= 0;
      syncVideoState();
    };

    const selectEvent = async (eventId) => {
      try {
        showDetail.value = true;
        curEvent.value = null;
        await refreshSelectedEvent(eventId);
      } catch (error) {
        showDetail.value = false;
        message.error(error.message || "事件详情加载失败");
      }
    };

    onMounted(async () => {
      await refreshStatus();
      startPolling();
    });

    onBeforeUnmount(() => {
      if (timer.value) {
        clearInterval(timer.value);
      }
    });

    return {
      loading,
      starting,
      status,
      curEvent,
      showDetail,
      loadingDetail,
      events,
      focusEventCount,
      normalEventCount,
      video,
      playing,
      volume,
      levelColor,
      reminderColor,
      statusText,
      formatRatio,
      mediaUrl,
      startMonitor,
      selectEvent,
      refreshStatus,
      toggleVideoPlayback,
      updateVideoVolume,
      syncVideoState,
    };
  },
  template: `
    <div class="page-shell">
      <div class="page-header">
        <div>
          <h1 class="page-title">课堂异常行为监测</h1>
          <div class="page-subtitle">
            教室监控实时检测，请及时关注异常提醒。
          </div>
        </div>
        <div class="meta-strip" v-if="status">
          <div class="meta-card">
            <div class="meta-label">监控状态</div>
            <div class="meta-value">
              {{ status.running ? '监控中' : (status.completed ? '已完成' : '待启动') }}
            </div>
          </div>
          <div class="meta-card">
            <div class="meta-label">已分析到</div>
            <div class="meta-value">{{ status.current_time }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">异常事件数</div>
            <div class="meta-value">{{ status.event_count }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">监测间隔</div>
            <div class="meta-value">{{ status.frame_interval_seconds }} 秒</div>
          </div>
        </div>
      </div>

      <a-spin :spinning="loading">
        <template v-if="status">
          <div class="hero-layout">
            <div class="surface-card video-panel">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px;">
                <h2 class="panel-title">监控主画面</h2>
                <div style="display:flex;gap:10px;">
                  <a-button @click="refreshStatus()">刷新</a-button>
                  <a-button type="primary" :loading="starting" @click="startMonitor">
                    启动监控
                  </a-button>
                </div>
              </div>

              <div class="video-box">
                <video
                  ref="video"
                  v-if="status.video_url"
                  :src="mediaUrl(status.video_url)"
                  muted
                  playsinline
                  @play="syncVideoState"
                  @pause="syncVideoState"
                  @volumechange="syncVideoState"
                ></video>
                <button
                  type="button"
                  class="video-overlay-control video-play-toggle"
                  @click="toggleVideoPlayback"
                  :title="playing ? '暂停' : '播放'"
                >
                  {{ playing ? '⏸' : '▶' }}
                </button>
                <div class="video-sound-control">
                  <input
                    class="video-volume-slider"
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    :value="volume"
                    @input="updateVideoVolume"
                  />
                </div>
              </div>
            </div>

            <div class="surface-card event-panel">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-end;margin-bottom:14px;">
                <div>
                  <h2 class="panel-title">异常事件列表</h2>
                  <div class="panel-note">
                    点击卡片查看异常分析详情
                  </div>
                </div>
                <div class="event-stat-strip">
                  <div class="event-stat-chip">
                    <span class="event-stat-label">总数</span>
                    <strong>{{ events.length }}</strong>
                  </div>
                  <div class="event-stat-chip strong">
                    <span class="event-stat-label">重点提醒</span>
                    <strong>{{ focusEventCount }}</strong>
                  </div>
                  <div class="event-stat-chip weak">
                    <span class="event-stat-label">普通提醒</span>
                    <strong>{{ normalEventCount }}</strong>
                  </div>
                </div>
              </div>

              <div v-if="events.length" class="event-grid">
                <div
                  v-for="event in events"
                  :key="event.event_id"
                  class="event-card"
                  :class="{ 'is-active': curEvent && curEvent.event_id === event.event_id }"
                  @click="selectEvent(event.event_id)"
                >
                  <img
                    v-if="event.list_image_url"
                    class="event-card-thumb"
                    :src="mediaUrl(event.list_image_url)"
                    :alt="'event-' + event.event_id"
                  />
                  <div class="event-card-body">
                    <div class="event-card-top">
                      <div class="event-card-id">{{ event.list_title || '位置待确认，疑似异常' }}</div>
                      <a-tag :color="reminderColor(event.reminder_level)">{{ event.reminder_text }}</a-tag>
                    </div>
                    <div class="event-card-text" :title="event.list_description || (event.list_description_error ? '模型调用失败' : '正在生成异常描述...')">
                      {{ event.list_description || (event.list_description_error ? '模型调用失败' : '正在生成异常描述...') }}
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="empty-state">暂无异常。</div>
            </div>
          </div>
        </template>
      </a-spin>

      <a-modal
        v-model:open="showDetail"
        :footer="null"
        width="1200px"
        centered
        destroyOnClose
      >
        <template #title>
          <span v-if="curEvent">{{ curEvent.list_title || ('事件 ' + String(curEvent.event_id).padStart(3, '0')) }}</span>
          <span v-else>异常详情</span>
        </template>

        <div v-if="loadingDetail" class="detail-loading-shell">
          <div class="detail-loading-card">
            <div class="detail-loading-line detail-loading-line-lg"></div>
            <div class="detail-loading-line detail-loading-line-md"></div>
            <div class="detail-loading-grid">
              <div class="detail-loading-block"></div>
              <div class="detail-loading-block"></div>
              <div class="detail-loading-block"></div>
              <div class="detail-loading-block"></div>
            </div>
            <div class="detail-loading-gallery">
              <div class="detail-loading-frame"></div>
              <div class="detail-loading-frame"></div>
              <div class="detail-loading-frame"></div>
            </div>
          </div>
        </div>
        <template v-else-if="curEvent">
          <div class="modal-detail-body">
            <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;">
              <div>
                <div class="panel-note">{{ curEvent.summary_text }}</div>
              </div>
              <a-tag :color="reminderColor(curEvent.reminder_level)" style="font-size:14px;padding:6px 12px;">
                {{ curEvent.reminder_text }}
              </a-tag>
            </div>

            <div class="summary-grid">
              <div class="summary-card">
                <div class="summary-label">提醒级别</div>
                <div class="summary-value">{{ curEvent.reminder_text }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">时间区间</div>
                <div class="summary-value">{{ curEvent.alert_start_time || curEvent.start_time }}</div>
                <div class="summary-subvalue">至 {{ curEvent.end_time }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">持续秒数</div>
                <div class="summary-value">{{ curEvent.duration_seconds }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">峰值比例</div>
                <div class="summary-value">{{ formatRatio(curEvent.peak_ratio) }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">峰值学生 ID</div>
                <div class="summary-value">{{ curEvent.peak_person_id }}</div>
              </div>
            </div>

            <div style="margin-top:22px;">
              <h3 class="panel-title" style="margin-bottom:6px;">异常明细</h3>
              <div class="panel-note">按抽取帧显示异常聚焦截图</div>

              <div class="detail-record-grid">
                <div
                  v-for="record in (curEvent.frames || [])"
                  :key="record.frame_index + '-' + record.person.id"
                  class="detail-record-card"
                >
                  <img
                    v-if="record.focus_image_url"
                    class="detail-record-image"
                    :src="mediaUrl(record.focus_image_url)"
                    alt="frame-focus"
                  />
                  <div class="detail-record-body">
                    <div class="detail-record-header">
                      <strong>第 {{ record.frame_index }} 帧</strong>
                      <a-tag :color="levelColor(record.person.status)">{{ record.person.status_text || statusText(record.person.status) }}</a-tag>
                    </div>
                    <div class="detail-record-meta">
                      <span>时间 {{ record.time }}</span>
                      <span>学生ID {{ record.person.id }}</span>
                      <span>比例值 {{ formatRatio(record.person.ratio) }}</span>
                      <span>置信度 {{ record.person.box_conf }}</span>
                    </div>
                    <div class="panel-note">位置：{{ record.person.position_text }}</div>
                  </div>
                </div>
              </div>

              <div
                v-if="!curEvent.frames || !curEvent.frames.length"
                class="empty-state"
              >
                当前事件没有可用的异常明细。
              </div>
            </div>
          </div>
        </template>
        <div v-else class="empty-state">当前事件详情暂时不可用。</div>
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
