import { createApp, ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";

import {
  Alert,
  Button,
  Modal,
  Spin,
  Tag,
  Table,
  TableColumn} from './antd.esm.js'

const API_BASE = window.MONITOR_API_BASE || "http://127.0.0.1:8001";

const App = {
  setup() {
    const loading = ref(true);
    const starting = ref(false);
    const describing = ref({});
    const statusData = ref(null);
    const selectedEvent = ref(null);
    const detailVisible = ref(false);
    const errorMessage = ref("");
    const infoMessage = ref("");
    const pollTimer = ref(null);
    const videoRef = ref(null);

    const levelColor = (level) => {
      if (level === "STRONG") return "red";
      if (level === "WEAK") return "gold";
      return "blue";
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

    const events = computed(() => statusData.value?.events || []);
    const hasSelection = computed(() => !!selectedEvent.value);

    const refreshSelectedEvent = async (eventId) => {
      selectedEvent.value = await requestJson(`/api/events/${eventId}`);
    };

    const refreshStatus = async (keepSelection = true) => {
      try {
        const status = await requestJson("/api/monitor/status");
        statusData.value = status;

        if (!status.events.length) {
          selectedEvent.value = null;
          return;
        }

        const eventId = keepSelection && selectedEvent.value
          ? selectedEvent.value.event_id
          : status.events[0].event_id;

        const picked = status.events.find((item) => item.event_id === eventId) || status.events[0];
        await refreshSelectedEvent(picked.event_id);
      } catch (error) {
        errorMessage.value = error.message || "状态加载失败";
      } finally {
        loading.value = false;
      }
    };

    const startPolling = () => {
      if (pollTimer.value) {
        clearInterval(pollTimer.value);
      }
      pollTimer.value = setInterval(() => {
        refreshStatus();
      }, 2000);
    };

    const startMonitor = async () => {
      starting.value = true;
      errorMessage.value = "";
      infoMessage.value = "";

      try {
        const result = await requestJson("/api/monitor/start", { method: "POST" });
        infoMessage.value = result.message || "监控已启动";
        await refreshStatus(false);

        await nextTick();
        if (videoRef.value) {
          videoRef.value.currentTime = 0;
          await videoRef.value.play().catch(() => {});
        }
      } catch (error) {
        errorMessage.value = error.message || "启动监控失败";
      } finally {
        starting.value = false;
      }
    };

    const selectEvent = async (eventId) => {
      try {
        selectedEvent.value = await requestJson(`/api/events/${eventId}`);
        detailVisible.value = true;
      } catch (error) {
        errorMessage.value = error.message || "事件详情加载失败";
      }
    };

    const describeCrop = async (eventId, personId) => {
      const key = `${eventId}_${personId}`;
      describing.value[key] = true;
      errorMessage.value = "";
      try {
        await requestJson(`/api/events/${eventId}/persons/${personId}/describe`, { method: "POST" });
        await refreshSelectedEvent(eventId);
      } catch (error) {
        errorMessage.value = error.message || "描述生成失败";
      } finally {
        describing.value[key] = false;
      }
    };

    onMounted(async () => {
      await refreshStatus(false);
      startPolling();
    });

    onBeforeUnmount(() => {
      if (pollTimer.value) {
        clearInterval(pollTimer.value);
      }
    });

    return {
      loading,
      starting,
      describing,
      statusData,
      selectedEvent,
      detailVisible,
      hasSelection,
      events,
      errorMessage,
      infoMessage,
      videoRef,
      levelColor,
      formatRatio,
      mediaUrl,
      startMonitor,
      selectEvent,
      describeCrop,
      refreshStatus,
    };
  },
  template: `
    <div class="page-shell">
      <div class="page-header">
        <div>
          <h1 class="page-title">课堂异常事件 Demo</h1>
          <div class="page-subtitle">
            前端和后端独立运行。左侧模拟实时监控，右侧通过接口持续拉取异常事件。
          </div>
        </div>
        <div class="meta-strip" v-if="statusData">
          <div class="meta-card">
            <div class="meta-label">视频时长</div>
            <div class="meta-value">{{ statusData.duration_time }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">已分析到</div>
            <div class="meta-value">{{ statusData.current_time }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">异常事件数</div>
            <div class="meta-value">{{ statusData.event_count }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">状态</div>
            <div class="meta-value">
              {{ statusData.running ? '监控中' : (statusData.completed ? '已完成' : '待启动') }}
            </div>
          </div>
        </div>
      </div>

      <a-alert
        v-if="errorMessage"
        type="error"
        :message="errorMessage"
        show-icon
        style="margin-bottom: 16px;"
      />
      <a-alert
        v-if="infoMessage"
        type="info"
        :message="infoMessage"
        show-icon
        style="margin-bottom: 16px;"
      />

      <a-spin :spinning="loading">
        <template v-if="statusData">
          <div class="hero-layout">
            <div class="surface-card video-panel">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px;">
                <div>
                  <h2 class="panel-title">监控主画面</h2>
                  <div class="panel-note">
                    点击启动后，视频播放和后端分析会同步推进，右侧异常信息会陆续出现。
                  </div>
                </div>
                <div style="display:flex;gap:10px;">
                  <a-button @click="refreshStatus()">刷新</a-button>
                  <a-button type="primary" :loading="starting" @click="startMonitor">
                    启动监控
                  </a-button>
                </div>
              </div>

              <div class="video-box">
                <video
                  ref="videoRef"
                  v-if="statusData.video_url"
                  :src="mediaUrl(statusData.video_url)"
                  controls
                  muted
                ></video>
              </div>
            </div>

            <div class="surface-card event-panel">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-end;margin-bottom:14px;">
                <div>
                  <h2 class="panel-title">异常事件列表</h2>
                  <div class="panel-note">
                    这里通过接口轮询后端结果，不再预先离线读取本地 JSON。
                  </div>
                </div>
              </div>

              <div v-if="events.length" class="event-grid">
                <div
                  v-for="event in events"
                  :key="event.event_id"
                  class="event-card"
                  :class="{ 'is-active': selectedEvent && selectedEvent.event_id === event.event_id }"
                  @click="selectEvent(event.event_id)"
                >
                  <img
                    v-if="event.event_debug_image_url"
                    class="event-card-thumb"
                    :src="mediaUrl(event.event_debug_image_url)"
                    :alt="'event-' + event.event_id"
                  />
                  <div class="event-card-body">
                    <div class="event-card-top">
                      <div class="event-card-id">事件 {{ String(event.event_id).padStart(3, '0') }}</div>
                      <a-tag :color="levelColor(event.level)">{{ event.level }}</a-tag>
                    </div>
                    <div class="event-card-time">{{ event.start_time }} ~ {{ event.end_time }}</div>
                    <div class="event-card-time">持续 {{ event.frame_count }} 帧 | 峰值比例 {{ formatRatio(event.peak_ratio) }}</div>
                  </div>
                </div>
              </div>
              <div v-else class="empty-state">监控已启动后，这里会逐步出现异常事件。</div>
            </div>
          </div>
        </template>
      </a-spin>

      <a-modal
        v-model:open="detailVisible"
        :footer="null"
        width="1200px"
        centered
        destroyOnClose
      >
        <template #title>
          <span v-if="selectedEvent">事件 {{ String(selectedEvent.event_id).padStart(3, '0') }}</span>
        </template>

        <template v-if="selectedEvent">
          <div class="modal-detail-body">
            <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;">
              <div>
                <div class="panel-note">{{ selectedEvent.summary }}</div>
              </div>
              <a-tag :color="levelColor(selectedEvent.level)" style="font-size:14px;padding:6px 12px;">
                {{ selectedEvent.level }}
              </a-tag>
            </div>

            <div class="summary-grid">
              <div class="summary-card">
                <div class="summary-label">开始时间</div>
                <div class="summary-value">{{ selectedEvent.start_time }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">结束时间</div>
                <div class="summary-value">{{ selectedEvent.end_time }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">持续秒数</div>
                <div class="summary-value">{{ selectedEvent.duration_seconds }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">持续帧数</div>
                <div class="summary-value">{{ selectedEvent.frame_count }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">峰值比例</div>
                <div class="summary-value">{{ formatRatio(selectedEvent.peak_ratio) }}</div>
              </div>
              <div class="summary-card">
                <div class="summary-label">峰值学生 ID</div>
                <div class="summary-value">{{ selectedEvent.peak_person_id }}</div>
              </div>
            </div>

            <div class="detail-hero">
              <img
                v-if="selectedEvent.event_debug_image_url"
                class="detail-image"
                :src="mediaUrl(selectedEvent.event_debug_image_url)"
                alt="event-debug"
              />
              <img
                v-if="selectedEvent.event_raw_image_url"
                class="detail-image"
                :src="mediaUrl(selectedEvent.event_raw_image_url)"
                alt="event-raw"
              />
            </div>

            <div style="margin-top:22px;">
              <h3 class="panel-title" style="margin-bottom:6px;">异常学生截图</h3>
              <div class="panel-note">这里展示学生框和附近区域。描述由后端通过 LangChain 调通义千问多模态模型生成。</div>

              <div v-if="selectedEvent.event_crops && selectedEvent.event_crops.length" class="crop-grid">
                <div v-for="crop in selectedEvent.event_crops" :key="crop.image_url" class="crop-card">
                  <img class="crop-image" :src="mediaUrl(crop.image_url)" alt="event-crop" />
                  <div class="crop-body">
                    <div class="crop-title">
                      <strong>学生 {{ crop.person_id }}</strong>
                      <a-tag :color="levelColor(crop.status)">{{ crop.status }}</a-tag>
                    </div>
                    <div class="panel-note" style="margin-bottom:12px;">比例值 {{ formatRatio(crop.ratio) }}</div>

                    <div v-if="crop.description" class="description-box">
                      {{ crop.description }}
                    </div>
                    <div v-else class="placeholder-box">
                      还没有异常描述。
                    </div>

                    <a-button
                      type="primary"
                      block
                      style="margin-top:12px;"
                      :loading="describing[selectedEvent.event_id + '_' + crop.person_id]"
                      @click="describeCrop(selectedEvent.event_id, crop.person_id)"
                    >
                      生成异常描述
                    </a-button>
                  </div>
                </div>
              </div>
              <div v-else class="empty-state">当前事件没有可用的人物聚焦截图。</div>
            </div>

            <div class="table-wrap">
              <h3 class="panel-title" style="margin-bottom:10px;">事件内帧记录</h3>
              <a-table
                size="middle"
                :pagination="{ pageSize: 6, hideOnSinglePage: true }"
                :data-source="selectedEvent.frames"
                :row-key="(row) => row.frame_index + '-' + row.person.id"
              >
                <a-table-column title="帧号" data-index="frame_index" key="frame_index" />
                <a-table-column title="时间" data-index="time" key="time" />
                <a-table-column title="学生ID" key="person_id">
                  <template #default="{ record }">{{ record.person.id }}</template>
                </a-table-column>
                <a-table-column title="状态" key="status">
                  <template #default="{ record }">
                    <a-tag :color="levelColor(record.person.status)">{{ record.person.status }}</a-tag>
                  </template>
                </a-table-column>
                <a-table-column title="比例值" key="ratio">
                  <template #default="{ record }">{{ formatRatio(record.person.ratio) }}</template>
                </a-table-column>
                <a-table-column title="置信度" key="box_conf">
                  <template #default="{ record }">{{ record.person.box_conf }}</template>
                </a-table-column>
              </a-table>
            </div>
          </div>
        </template>
      </a-modal>
    </div>
  `,
};

const app = createApp(App);

app.use(Alert);
app.use(Button);
app.use(Modal);
app.use(Spin);
app.use(Tag);
app.use(Table);
app.use(TableColumn);

app.mount("#app");
