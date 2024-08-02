<template>

    <div class="w-full bg-white px-8 py-4 mt-4 border">
        <div class="flex justify-between items-center">
            <div class="font-bold text-xl mt-1 text-gray-800">Services</div>
            <button @click="fetchServicesHealth" class="text-gray-800 text-sm  mr-1"><UIcon name="material-symbols:refresh" class="text-gray-800 text-lg  mr-1" dynamic /></button>
            

        </div>
        
        <div class="font-semibold mt-2 h-1 border-b"></div>
        <div class="flex flex-wrap ">
            <div v-for="service in services" class="py-0 w-60 h-20 border-r border- my-4 pr-4  mr-3 bg-white">
                <div class="font-  mb-3 text-gray-800">{{ service['service_name'] }}</div>
                <div class="text-sm flex justify-start items-center text-gray-800">
                    <UIcon name="solar:check-square-bold" class="text-green-500  mr-1" dynamic
                        v-if="service['status'] === 'healthy'" />
                    <UIcon name="solar:close-square-bold" class="text-red-500  mr-1" dynamic v-else />
                    {{ service['status'] }}
                </div>
            </div>

            
        </div>
    </div>

    <div class="p-4 border my-3 bg-white">
        <ApplicationsTable />
    </div>

</template>

<script setup lang="ts">

definePageMeta({
    layout: "shell",
    middleware: "auth"
})

import { onMounted } from 'vue';

const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl
const services = ref([]);


async function fetchServicesHealth() {
    const { data, pending, error, refresh, execute } = await useFetch(BASE_URL + 'admin/platform/services/health', {
        immediate: true,
        credentials: 'include',
        onResponse: (context) => {
            console.log(context.response._data);
            services.value = context.response._data;
        },
        onResponseError: (context) => {
            console.log(context.response._data);
        }
    });
    await execute();
}

onMounted(() => {
    console.log('Dashboard Page Mounted');
    fetchServicesHealth();
});

</script>