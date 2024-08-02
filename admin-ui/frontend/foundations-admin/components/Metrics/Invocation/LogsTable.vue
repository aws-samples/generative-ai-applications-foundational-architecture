<script setup lang="ts">
import { list } from 'postcss';


const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl

const isOpen = ref(false);
const app_name = ref('');
const description = ref('');
const toast = useToast();

const columns = [{
    key: 'model_name',
    label: 'Model'
}, {
    key: 'total_count',
    label: '# Invocations'
}, {
    key: 'status_counts.SUCCESS',
    label: 'Success Count'
},
{
    key: 'status_counts.FAILED',
    label: 'Failed Count'
},
{
    key: 'total_input_tokens',
    label: 'Total Input Tokens'
}
    ,
{
    key: 'total_output_tokens',
    label: 'Total Output Tokens'
}
]

const props = defineProps({
  logs: {
    type: Array,
    required: true
  }
});
const { logs } = toRefs(props);

</script>

<template>
   
  <UTable :rows="logs" :columns="columns" class="border text-gray-800">

    </UTable>   

</template>