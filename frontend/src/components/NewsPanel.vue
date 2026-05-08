<template>
  <div class="news-dashboard">
    <div class="news-header-bar">
      <span class="news-logo">Hot News</span>
      <span class="news-subtitle">{{ currentPlatformLabel }} 实时热点</span>
    </div>

    <div class="news-platform-tabs">
      <button
        v-for="platform in newsPlatforms"
        :key="platform.key"
        class="platform-chip"
        :class="{ active: currentPlatform === platform.key }"
        type="button"
        @click="switchNewsPlatform(platform.key)"
      >
        {{ platform.label }}
      </button>
    </div>

    <div v-if="newsLoading" class="news-loading">
      <div class="loading-dot-pulse"></div>
      <span>获取热点中...</span>
    </div>

    <div v-else class="news-list">
      <a
        v-for="(item, idx) in newsItems"
        :key="`${currentPlatform}_${idx}_${item.title || item.url || ''}`"
        v-motion
        :initial="{ opacity: 0, y: 20 }"
        :enter="{ opacity: 1, y: 0, transition: { delay: idx * 28, duration: 320, ease: [0.16, 1, 0.3, 1] } }"
        :href="item.url"
        target="_blank"
        rel="noreferrer"
        class="news-card"
      >
        <div class="news-rank" :class="rankClass(idx)">{{ idx + 1 }}</div>
        <div class="news-body">
          <div class="news-title">{{ item.title }}</div>
          <div v-if="item.desc || item.content" class="news-meta">
            <span class="news-desc">{{ item.desc || item.content }}</span>
          </div>
        </div>
        <div v-if="item.score || item.publish_time" class="news-score">
          <span class="score-value">{{ item.publish_time ? item.publish_time.slice(-8) : formatScore(item.score) }}</span>
        </div>
      </a>

      <div v-if="!newsItems.length && !newsLoading" class="news-empty">
        暂无热点数据
      </div>
    </div>

    <div class="news-footer">
      <span class="footer-status" :class="{ live: !newsLoading }">
        <span class="status-dot"></span>
        {{ newsLoading ? '加载中' : `更新于 ${lastNewsUpdate || '--:--:--'}` }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';

const emit = defineEmits(['news-changed']);

const NEWS_PLATFORMS = [
  { key: 'weibo', label: '微博' },
  { key: 'zhihu', label: '知乎' },
  { key: 'baidu', label: '百度' },
  { key: 'bilibili', label: 'B站' },
  { key: 'tskr', label: '36氪' },
  { key: 'github', label: 'GitHub' },
  { key: 'juejin', label: '掘金' },
  { key: 'hackernews', label: 'HN' },
  { key: 'douyin', label: '抖音' },
  { key: 'vtex', label: 'V2EX' },
  { key: 'tieba', label: '贴吧' },
  { key: 'jinritoutiao', label: '头条' }
];

const NEWS_API_BASE = 'https://orz.ai/api/v1/dailynews';
const NEWS_REFRESH_INTERVAL = 10 * 60 * 1000;

const currentPlatform = ref('weibo');
const newsItems = ref([]);
const newsLoading = ref(false);
const lastNewsUpdate = ref('');
let newsTimer = null;

const newsPlatforms = computed(() => NEWS_PLATFORMS);
const currentPlatformLabel = computed(() => {
  const platform = NEWS_PLATFORMS.find((item) => item.key === currentPlatform.value);
  return platform?.label || currentPlatform.value;
});

function formatScore(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n)) return '';
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function rankClass(idx) {
  if (idx === 0) return 'rank-top1';
  if (idx === 1) return 'rank-top2';
  if (idx === 2) return 'rank-top3';
  return '';
}

async function fetchNews(platform) {
  newsLoading.value = true;
  try {
    const resp = await fetch(`${NEWS_API_BASE}/?platform=${platform}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();

    if (json.status === '200' && Array.isArray(json.data)) {
      newsItems.value = json.data.slice(0, 25);
      const now = new Date();
      lastNewsUpdate.value = [
        String(now.getHours()).padStart(2, '0'),
        String(now.getMinutes()).padStart(2, '0'),
        String(now.getSeconds()).padStart(2, '0')
      ].join(':');
    } else {
      newsItems.value = [];
    }
  } catch {
    newsItems.value = [];
  } finally {
    newsLoading.value = false;
  }
}

function switchNewsPlatform(platform) {
  if (currentPlatform.value === platform) return;
  currentPlatform.value = platform;
  emit('news-changed', platform);
  void fetchNews(platform);
}

onMounted(() => {
  void fetchNews(currentPlatform.value);
  newsTimer = window.setInterval(() => fetchNews(currentPlatform.value), NEWS_REFRESH_INTERVAL);
});

onUnmounted(() => {
  if (newsTimer) window.clearInterval(newsTimer);
});
</script>

<style scoped>
.news-dashboard {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  color: var(--text-primary);
  background: transparent;
}

.news-header-bar {
  padding: var(--space-lg) var(--space-lg) var(--space-sm);
  flex-shrink: 0;
}

.news-logo {
  display: block;
  font-family: var(--font-display);
  font-size: var(--font-size-xl);
  font-weight: 700;
  line-height: 1.2;
  color: var(--neon-cyan);
}

.news-subtitle {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.news-platform-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 var(--space-lg) var(--space-md);
  flex-shrink: 0;
}

.platform-chip {
  padding: 5px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out-expo),
    border-color var(--duration-fast) var(--ease-out-expo),
    color var(--duration-fast) var(--ease-out-expo);
}

.platform-chip:hover,
.platform-chip.active {
  border-color: var(--border-active);
  color: var(--neon-cyan);
  background: var(--neon-cyan-dim);
}

.news-loading {
  display: grid;
  place-items: center;
  gap: var(--space-md);
  padding: var(--space-2xl);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.loading-dot-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--neon-cyan);
  animation: dotPulse 1.2s var(--ease-out-expo) infinite;
}

@keyframes dotPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(71, 215, 198, 0.6); }
  50% { box-shadow: 0 0 0 12px rgba(71, 215, 198, 0); }
}

.news-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 var(--space-md);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.news-card {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  padding: 10px var(--space-sm);
  border-radius: var(--radius-sm);
  text-decoration: none;
  color: inherit;
  transition: background var(--duration-fast) var(--ease-out-expo);
}

.news-card:hover {
  background: var(--surface-0);
}

.news-rank {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--text-muted);
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.2);
}

.rank-top1 { color: #f0b35a; background: rgba(240, 179, 90, 0.12); }
.rank-top2 { color: #a0b8c8; background: rgba(160, 184, 200, 0.1); }
.rank-top3 { color: #c89070; background: rgba(200, 144, 112, 0.1); }

.news-body {
  flex: 1;
  min-width: 0;
}

.news-title {
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color var(--duration-fast);
}

.news-card:hover .news-title {
  color: var(--neon-cyan);
}

.news-desc {
  margin-top: 2px;
  font-family: var(--font-body);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-score {
  flex-shrink: 0;
}

.score-value {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  background: rgba(0, 0, 0, 0.25);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.news-empty {
  padding: var(--space-2xl);
  text-align: center;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}

.news-footer {
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.footer-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
}

.footer-status.live {
  color: var(--neon-green);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.footer-status.live .status-dot {
  animation: dotPulse 2s var(--ease-out-expo) infinite;
}

@container (max-width: 420px), (max-height: 260px) {
  .news-footer {
    display: none;
  }

  .news-header-bar {
    padding: 10px 12px 6px;
  }

  .news-platform-tabs {
    padding: 0 10px 8px;
    flex-wrap: nowrap;
    overflow-x: auto;
  }

  .news-card {
    padding: 8px 6px;
  }
}
</style>
