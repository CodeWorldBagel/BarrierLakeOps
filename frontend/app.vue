<template>
  <div>
    <header class="app-header">
      <div class="brand">
        <NuxtLink to="/" style="color: var(--text)">
          <b>BarrierLakeOps</b>
        </NuxtLink>
        <span>堰湖態勢跨部會研判</span>
      </div>
      <nav>
        <NuxtLink to="/">主控台</NuxtLink>
        <NuxtLink to="/about">關於</NuxtLink>
        <a :href="apiDocs" target="_blank" rel="noopener">API 文件 ↗</a>
      </nav>
    </header>
    <NuxtPage />
  </div>
</template>

<script setup lang="ts">
const apiDocs = (useRuntimeConfig().public.apiBase as string) + "/docs";
</script>
