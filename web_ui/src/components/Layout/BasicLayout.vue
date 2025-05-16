<template>
  <a-layout>
    <Navbar />
    <a-layout-content>
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import Navbar from './Navbar.vue'
</script>