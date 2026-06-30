<template>
  <header class="app-header">
    <div class="brand">
      <NuxtLink to="/" class="brand-link">
        <img src="/logo.png" alt="BarrierLakeOps logo" class="brand-logo" />
        <b>BarrierLakeOps</b>
      </NuxtLink>
      <span>堰湖態勢跨部會研判</span>
    </div>

    <!-- 桌機 nav -->
    <nav class="desk-nav">
      <NuxtLink to="/">主控台</NuxtLink>
      <NuxtLink to="/connect">接上 MCP</NuxtLink>
      <NuxtLink to="/data">資料同步</NuxtLink>
      <NuxtLink to="/about">關於</NuxtLink>
    </nav>

    <!-- 漢堡按鈕（md 以下顯示） -->
    <button class="burger" aria-label="開啟選單" @click="menuOpen = !menuOpen">
      <span /><span /><span />
    </button>

    <!-- 手機下拉選單 -->
    <div v-if="menuOpen" class="mobile-nav" @click="menuOpen = false">
      <NuxtLink to="/">主控台</NuxtLink>
      <NuxtLink to="/connect">接上 MCP</NuxtLink>
      <NuxtLink to="/data">資料同步</NuxtLink>
      <NuxtLink to="/about">關於</NuxtLink>
    </div>

    <!-- 點選單外關閉 overlay -->
    <div v-if="menuOpen" class="nav-overlay" @click="menuOpen = false" />
  </header>
</template>

<script setup lang="ts">
const menuOpen = ref(false)
const route = useRoute()
watch(() => route.path, () => { menuOpen.value = false })
</script>

<style scoped>
.desk-nav a { margin-left: 20px; color: var(--text); font-size: 13px; letter-spacing: .5px; }

.burger {
  display: none;
  flex-direction: column; justify-content: center; align-items: center;
  gap: 5px; width: 36px; height: 36px;
  background: none; border: none; cursor: pointer; padding: 6px;
}
.burger span {
  display: block; width: 20px; height: 2px;
  background: var(--text); border-radius: 2px;
}

.mobile-nav {
  position: absolute; top: 100%; left: 0; right: 0;
  background: var(--panel); border-bottom: 1px solid var(--border);
  z-index: 999; display: flex; flex-direction: column;
}
.mobile-nav a {
  padding: 14px 22px; color: var(--text); font-size: 15px;
  border-bottom: 1px solid var(--border-soft);
}
.mobile-nav a:hover { background: var(--panel-2); text-decoration: none; }

.nav-overlay {
  position: fixed; inset: 0; z-index: 998;
}

@media (max-width: 768px) {
  .desk-nav { display: none; }
  .burger { display: flex; }
}
</style>
