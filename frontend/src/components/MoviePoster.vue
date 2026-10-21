<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Film } from '@element-plus/icons-vue'
/**
 * 海报优先级：
 *   1) localPath —— 本地 public/posters/{movie_id}.jpg（OMDb 下载，离线可用）
 *   2) path       —— TMDB poster_path（image.tmdb.org CDN，部分网络环境被封）
 *   3) 都没有     —— 显示 Film icon 占位
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
    return props.localPath  // Vite public 目录文件原样输出
  }
  if (props.path && /^\/[a-zA-Z0-9._-]+\.(jpg|png|webp)$/.test(props.path)) {
    return `https://image.tmdb.org/t/p/w342${props.path}`
  }
  return null
})
</script>
<template>
  <div class="movie-poster">
    <img v-if="src && !failed" :src="src" :alt="title + '海报'" loading="lazy" @error="failed = true" />
    <div v-else class="poster-placeholder" role="img" :aria-label="title + '：暂无海报'">
      <span class="frame-corner top" aria-hidden="true" /><el-icon aria-hidden="true"><Film /></el-icon><span>暂无海报</span><small>CINELAB ARCHIVE</small><span class="frame-corner bottom" aria-hidden="true" />
    </div>
  </div>
</template>
