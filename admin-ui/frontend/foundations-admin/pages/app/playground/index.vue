<template>
    <div class="px-8 py-4 font-bold text-lg border mt-3 bg-white">
        API Endpoints
    </div>
    <div class="p-4 border bg-white">
        <div id="swagger-ui">
        </div>
    </div>

</template>

<style scoped>
* >>> .information-container {
    display: none;
}

* >>> .opblock-tag {
    font-size: 20px !important;
    font-weight: 600;
}

* >>> h1,* >>> h2, * >>> h3, * >>> h4, * >>> h5, * >>> h6 {
    font-weight: 600 !important;
}

* >>> h2 {
    font-size: 20px !important;
}

* >>> h4 {
    font-size: 20px !important;
}

* >>> code {
    color: #ffffff !important;
    background: #333333 !important;
    font-weight: 400 !important;
}

* >>> hr {
    margin: 20px 0 !important;
}
</style>

<script setup lang="ts">

definePageMeta({
    layout: "shell",
    middleware: "auth"
})



import { onMounted } from 'vue';

const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl;

const ui_html = ref('');

useHead({
    title: 'Generative AI Foundations',
    meta: [
        {
            name: 'description',
            content: 'API Playground'
        }
    ],
    script: [
        {
            src: '/swagger-ui-bundle.js',
            type: 'text/javascript'
        }
    ],
    link: [
        {
            rel: 'stylesheet',
            href: '/swagger-ui.css'
        }
    ]
});


async function fetchData() {
    const { data, pending, error, refresh, execute } = await useFetch(BASE_URL + 'admin/platform/openapi.json', {
        immediate: true,
        credentials: 'include',
        onResponse: (context) => {
            console.log(context.response._data);
            ui_html.value = context.response._data.toString();
            const ui = window.SwaggerUIBundle({
                spec: context.response._data,
                dom_id: '#swagger-ui',
                presets: [window.SwaggerUIBundle.presets.apis, window.SwaggerUIStandalonePreset.slice(1)],
                layout: 'StandaloneLayout',
                requestInterceptor: (req) => {
                    const url = new URL(req.url);
                    const base = new URL(BASE_URL);
                    url.host = base.href;
                    url.protocol = base.protocol;
                    req.url = base.href + 'admin' + url.pathname
                    req.credentials = 'include';
                    return req;
                },
            });
        }
    });
    await execute();
}

async function fetchDocs(){
    const { data, pending, error, refresh, execute } = await useFetch(BASE_URL + 'admin/docs', {
        immediate: true,
        credentials: 'include',
        onResponse: (context) => {
            console.log(context.response._data);
        }
    });
    await execute();
}
onMounted(() => {
    setTimeout(() => {
        fetchData();
        fetchDocs();
    }, 1000);
});

</script>