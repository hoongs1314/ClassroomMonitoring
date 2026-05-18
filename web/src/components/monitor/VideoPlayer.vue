<script setup>
import { ref, computed, watch } from 'vue'
import {
  PauseOutlined,
  PlayCircleFilled,
  VideoCameraFilled,
} from '@ant-design/icons-vue'
import { useApi } from '@/composables/useApi'

const props = defineProps({
  mode: { type: String, default: 'mjpeg' },
  mjpegUrl: { type: String, default: '/video_feed' },
  videoUrl: { type: String, default: '' },
  live: { type: Boolean, default: false },
  imgW: { type: Number, default: 1920 },
  imgH: { type: Number, default: 1080 },
  seats: { type: Array, default: () => [] },
})

const { mediaUrl } = useApi()

const video = ref(null)
const playing = ref(false)
const volume = ref(0)
const videoProgress = ref(0)

const statusMap = {
  NORMAL: { c: '#22C55E', t: '正常' },
  HEAD_DOWN: { c: '#F59E0B', t: '低头' },
  DESK_LYING: { c: '#EF4444', t: '趴睡' },
  UNCERTAIN: { c: '#64748B', t: '模糊' },
  SUSPECTED: { c: '#F59E0B', t: '疑似' },
}
const getS = (s) => statusMap[s] || statusMap.NORMAL

const abnormalSeats = computed(() =>
  props.seats.filter((s) => !['NORMAL'].includes(s.status))
)

function getBoxStyle(box) {
  if (!box || !props.imgW) return { display: 'none' }
  return {
    left: `${(box[0] / props.imgW) * 100}%`,
    top: `${(box[1] / props.imgH) * 100}%`,
    width: `${((box[2] - box[0]) / props.imgW) * 100}%`,
    height: `${((box[3] - box[1]) / props.imgH) * 100}%`,
  }
}

function syncVideoState() {
  if (!video.value) return
  playing.value = !video.value.paused
  volume.value = Math.round((video.value.muted ? 0 : video.value.volume) * 100)
  updateVideoProgress()
}

function updateVideoProgress() {
  if (!video.value || !Number.isFinite(video.value.duration) || video.value.duration <= 0) {
    videoProgress.value = 0
    return
  }
  videoProgress.value = (video.value.currentTime / video.value.duration) * 100
}

async function togglePlay() {
  if (!video.value) return
  if (video.value.paused) {
    await video.value.play().catch(() => {})
  } else {
    video.value.pause()
  }
  syncVideoState()
}

function updateVolume(val) {
  if (!video.value) return
  const next = val / 100
  video.value.volume = next
  video.value.muted = next <= 0
  syncVideoState()
}

function seekVideo(val) {
  if (!video.value || !Number.isFinite(video.value.duration) || video.value.duration <= 0) return
  video.value.currentTime = (val / 100) * video.value.duration
  updateVideoProgress()
}
</script>

<template>
  <div class="video-player">
    <div class="viewport" :style="{ aspectRatio: `${imgW}/${imgH}` }">
      <!-- LIVE 徽章 -->
      <div v-if="live" class="live-badge">
        <span class="live-dot"></span>
        LIVE
      </div>

      <!-- MJPEG 流 -->
      <img
        v-if="mode === 'mjpeg' && mjpegUrl"
        :src="mediaUrl(mjpegUrl)"
        class="feed"
        alt="监控画面"
      />

      <!-- Video 元素 -->
      <video
        v-else-if="mode === 'video' && videoUrl"
        ref="video"
        :src="mediaUrl(videoUrl)"
        muted
        playsinline
        class="feed"
        @play="syncVideoState"
        @pause="syncVideoState"
        @volumechange="syncVideoState"
        @loadedmetadata="syncVideoState"
        @timeupdate="updateVideoProgress"
      ></video>

      <!-- 无信号 -->
      <div v-else class="no-signal">
        <VideoCameraFilled class="no-signal-icon" />
        <p>等待视频流...</p>
      </div>

      <!-- 异常检测框叠加 -->
      <div
        v-for="s in abnormalSeats"
        :key="s.seat_id"
        class="detect-rect"
        :style="[getBoxStyle(s.box), { borderColor: getS(s.status).c }]"
      >
        <span class="detect-label" :style="{ background: getS(s.status).c }">
          {{ s.seat_code }}
        </span>
      </div>

      <!-- 视频控制栏 -->
      <div v-if="mode === 'video' && videoUrl" class="video-controls">
        <button type="button" class="control-btn" :title="playing ? '暂停' : '播放'" @click="togglePlay">
          <PauseOutlined v-if="playing" />
          <PlayCircleFilled v-else />
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
          @input="(e) => updateVolume(Number(e.target.value))"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.video-player {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.viewport {
  position: relative;
  max-width: 100%;
  max-height: 100%;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: #000;
}

.feed {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.no-signal {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: 12px;
}
.no-signal-icon {
  font-size: 48px;
  opacity: 0.3;
}

.live-badge {
  position: absolute;
  left: 16px;
  top: 16px;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 12px;
  border-radius: 6px;
  background: var(--color-danger);
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 4px 16px rgba(239, 68, 68, 0.3);
}
.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #fff;
  animation: live-pulse 1.2s ease-in-out infinite;
}
@keyframes live-pulse {
  50% { opacity: 0.3; }
}

.detect-rect {
  position: absolute;
  border: 2px solid var(--color-danger);
  background: rgba(239, 68, 68, 0.08);
  z-index: 5;
  transition: all 0.3s var(--ease-out);
}
.detect-label {
  position: absolute;
  top: -22px;
  left: -2px;
  padding: 0 6px;
  height: 20px;
  line-height: 20px;
  font-size: 11px;
  font-weight: 800;
  color: #fff;
  border-radius: 4px 4px 0 0;
  white-space: nowrap;
}

.video-controls {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 16px;
  height: 52px;
  padding: 0 20px;
  background: linear-gradient(180deg, rgba(0,0,0,0.1), rgba(0,0,0,0.8));
}
.control-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #fff;
  font-size: 20px;
  cursor: pointer;
}
.control-btn:hover {
  background: rgba(255,255,255,0.12);
}
.progress-range {
  flex: 1;
  min-width: 100px;
  height: 4px;
  accent-color: var(--color-primary);
}
.volume-range {
  width: 120px;
  height: 4px;
  accent-color: var(--color-primary);
}
</style>
