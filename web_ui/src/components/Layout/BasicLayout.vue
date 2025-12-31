<template>
  <a-layout id="main" class="basic-layout">
    <a-layout-content class="basic-content">
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts"></script>

<style scoped>
.basic-layout {
  min-height: calc(100vh - var(--app-header-height));
}
</style>
