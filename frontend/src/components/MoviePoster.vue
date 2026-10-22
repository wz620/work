<script setup lang="ts">
import { computed, ref, watch } from 'vue'
/**
 * 海报优先级：
 *   1) localPath —— 本地 public/posters/{movie_id}.jpg
 *   2) path       —— TMDB poster_path（image.tmdb.org CDN）
 *   3) 都没有     —— 彩色渐变占位卡片（首字母 + 片名）
 */
const props = defineProps<{
  localPath?: string | null
  path?: string | null
  title: string
}>()
const failed = ref(false)
watch(() => [props.localPath, props.path], () => { failed.value = false })

const src = computed(() => {
  if (props.localPath && /^\/[a-zA-Z0-9_./-]+\.(jpg|jpeg|png|webp)$/.test(props.localPath)) {
    return props.localPath
  }
  if (props.path && /^\/[a-zA-Z0-9._-]+\.(jpg|png|webp)$/.test(props.path)) {
    return `https://image.tmdb.org/t/p/w342${props.path}`
  }
  return null
})

// Fallback 卡片的彩色背景（基于 title hash 选固定渐变）
const GRADIENTS = [
  'linear-gradient(135deg,#6366f1 0%,#ec4899 100%)',
  'linear-gradient(135deg,#f59e0b 0%,#ef4444 100%)',
  'linear-gradient(135deg,#10b981 0%,#06b6d4 100%)',
  'linear-gradient(135deg,#8b5cf6 0%,#3b82f6 100%)',
  'linear-gradient(135deg,#f43f5e 0%,#f59e0b 100%)',
  'linear-gradient(135deg,#14b8a6 0%,#6366f1 100%)',
  'linear-gradient(135deg,#e11d48 0%,#7c3aed 100%)',
  'linear-gradient(135deg,#0ea5e9 0%,#22c55e 100%)',
  'linear-gradient(135deg,#7c2d12 0%,#1e293b 100%)',
  'linear-gradient(135deg,#a855f7 0%,#f472b6 100%)',
]

const gradient = computed(() => {
  let h = 0
  for (const c of props.title) h = (h * 31 + c.charCodeAt(0)) & 0x7fffffff
  return GRADIENTS[h % GRADIENTS.length]
})

const initial = computed(() => {
  const t = props.title.trim()
  if (!t) return '?'
  return t[0].toUpperCase()
})

const shortTitle = computed(() => {
  const t = props.title.trim()
  return t.length > 22 ? t.slice(0, 20) + '…' : t
})
</script>
<template>
  <div class="movie-poster">
    <img v-if="src && !failed" :src="src" :alt="title + '海报'" loading="lazy" @error="failed = true" />
    <!-- 优雅 fallback：彩色渐变卡片 + 首字母 + 片名 -->
    <div v-else class="poster-fallback" :style="{ background: gradient }" role="img" :aria-label="title + '：暂无海报'">
      <span class="fallback-initial">{{ initial }}</span>
      <span class="fallback-title">{{ shortTitle }}</span>
      <span class="fallback-tag">暂无海报</span>
    </div>
  </div>
</template>
<style scoped>
.movie-poster {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  aspect-ratio: 3 / 4.2;
  background: #1e293b;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
.movie-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.poster-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  text-align: center;
  padding: 16px;
  position: relative;
  overflow: hidden;
}
.poster-fallback::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 30% 20%, rgba(255,255,255,0.15) 0%, transparent 50%);
  pointer-events: none;
}
.fallback-initial {
  font-size: 72px;
  font-weight: 800;
  line-height: 1;
  text-shadow: 0 2px 12px rgba(0,0,0,0.3);
  letter-spacing: -2px;
  opacity: 0.9;
}
.fallback-title {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
  text-shadow: 0 1px 4px rgba(0,0,0,0.4);
  max-width: 100%;
  z-index: 1;
}
.fallback-tag {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  opacity: 0.6;
  padding: 2px 8px;
  background: rgba(0,0,0,0.25);
  border-radius: 4px;
}
</style>
