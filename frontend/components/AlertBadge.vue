<template>
  <span class="badge" :class="level">
    <span class="dot" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
const props = defineProps<{ level: string }>();
const labels: Record<string, string> = {
  red: "紅色",
  orange: "橙色",
  yellow: "黃色",
  green: "綠色",
  unknown: "未知",
};
const label = computed(() => labels[props.level] || props.level);
</script>
