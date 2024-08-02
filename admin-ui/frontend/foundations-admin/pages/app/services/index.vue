<template>

    <div class="p-4 rounded-lg border my-3 bg-white">
        Services
    </div>
    <div v-for="service in services">
        {{ service['service_name'] }}
    </div>

</template>

<script setup lang="ts">

definePageMeta({
    layout: "shell",
    middleware: "auth"
})

import { onMounted } from 'vue';
const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl;
const services = ref([]);


async function fetchData() {
    const { data, pending, error, refresh, execute } = await useFetch(BASE_URL + 'admin/platform/services/health',{
        immediate: true,    
        credentials: 'include',
        onResponse: (context) => {
            console.log(context.response._data);
            services.value = context.response._data;
        }
    });
   await execute();
}


onMounted(() => {
    console.log('Dashboard Page Mounted');
    fetchData();
});

</script>