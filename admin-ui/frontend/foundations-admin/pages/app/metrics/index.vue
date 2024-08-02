<template>

  <div class="bg-white px-8 py-4 border-t mt-4 h-full">
    <div class=" pb-3 border-b font-bold text-xl mb-8">Metrics</div>
    <div class="text-sm italic mb-3 text-gray-500">Select Application and Date Range to fetch metrics</div>
    <div class="flex w-full justify-start gap-8 items-center">

      <div class="flex flex-col">
        <label for="app-select" class="text-sm mb-2 font-semibold">Application</label>
        <select v-model="selectedApp" id="app-select" class="p-2 w-64 border rounded">
          <option v-for="app in apps" :key="app.id" :value="app.id">
            {{ app.name }}
          </option>
        </select>
      </div>

      <div class="flex flex-col">
        <label for="start-date" class="text-sm mb-2 font-semibold">From</label>
        <input type="date" v-model="startDate" id="start-date" class="p-2 w-48 border rounded">
      </div>

      <div class="flex flex-col">
        <label for="end-date" class="text-sm mb-2 font-semibold">To</label>
        <input type="date" v-model="endDate" id="end-date" class="p-2 w-48 border rounded">
      </div>

      <button @click="fetchMetrics" class="mt-6 bg-white rounded-full text-blue-700 rounded-full border-blue-500 border-2 text-xs px-3 py-2 hover:bg-orange-500 hover:text-white hover:border-white">Fetch Metrics</button>
    </div>

    <div v-if="is_loading" class="flex justify-center items-center h-64">
      <UIcon name="svg-spinners:gooey-balls-2" class="text-xl text-gray-500" dynamic />
    </div>


    <div v-show="is_fetched" class="py-4">



      <div class="w-full my-4 bg-white py-4 border-t flex">

        <div class="flex h-12 gap-x-8 border-b">

          <button @click="setSubTab('invocations')" class="text-sm h-12" :class="{
          'sub-tab-active': sub_tab.includes('invocations'),
          'sub-tab': !sub_tab.includes('applications'),
        }">Model Invocations</button>
          <button @click="setSubTab('extraction_jobs')" class="h-12 text-sm" :class="{
          'sub-tab-active': sub_tab.includes('extraction_jobs'),
          'sub-tab': !sub_tab.includes('extraction_jobs'),
        }">Extraction Jobs</button>
          <button @click="setSubTab('chunking_jobs')" class="h-12 text-sm" :class="{
          'sub-tab-active': sub_tab.includes('chunking_jobs'),
          'sub-tab': !sub_tab.includes('chunking_jobs'),
        }">Chunking Jobs</button>
          <button @click="setSubTab('vectorization_jobs')" class="h-12 text-sm" :class="{
          'sub-tab-active': sub_tab.includes('vectorization_jobs'),
          'sub-tab': !sub_tab.includes('vectorization_jobs'),
        }">Vectorization Jobs</button>
          <!-- <button @click="setSubTab('vector_stores')" class="h-12 text-sm">Vector Stores</button> -->


        </div>

      </div>

      <div v-if="sub_tab === 'invocations'">
        <MetricsInvocationLogsTable :logs="metrics" />

      </div>

      <div v-if="sub_tab === 'extraction_jobs'" class="flex w-full">
        <table class="text-sm border border-gray-300 w-full">
          <tr class="py-2">
            <th class="py-3 px-4 text-left font-semibold">Job Status</th>
            <th class="py-3 px-4 text-left font-semibold"># of Jobs</th>
            <th class="py-3 px-4 text-left font-semibold">Total Files Processed</th>
            <th class="py-3 px-4 text-left font-semibold">Completed Files</th>
            <th class="py-3 px-4 text-left font-semibold">Failed Files</th>
          </tr>
          <tr v-for="(item, key, index) in extraction_jobs" class="border-t">
            <td class="py-3 px-4">{{ key }}</td>
            <td class="py-3 px-4">{{ item.total_count }}</td>
            <td class="py-3 px-4">{{ item.total_total_file_count }}</td>
            <td class="py-3 px-4">{{ item.total_completed_file_count }}</td>
            <td class="py-3 px-4">{{ item.total_failed_file_count }}</td>
          </tr>
        </table>

      </div>

      <div v-if="sub_tab === 'chunking_jobs'" class="flex w-full">
        <table class="text-sm border border-gray-300 w-full">
          <tr class="py-2">
            <th class="py-3 px-4 text-left font-semibold">Job Status</th>
            <th class="py-3 px-4 text-left font-semibold"># of Jobs</th>
            <th class="py-3 px-4 text-left font-semibold">Total Files Processed</th>
            <th class="py-3 px-4 text-left font-semibold">Completed Files</th>
            <th class="py-3 px-4 text-left font-semibold">Failed Files</th>
          </tr>
          <tr v-for="(item, key, index) in chunking_jobs" class="border-t">
            <td class="py-3 px-4">{{ key }}</td>
            <td class="py-3 px-4">{{ item.total_count }}</td>
            <td class="py-3 px-4">{{ item.total_total_files }}</td>
            <td class="py-3 px-4">{{ item.total_completed_files }}</td>
            <td class="py-3 px-4">{{ item.total_failed_files }}</td>
          </tr>
        </table>

      </div>

      <div v-if="sub_tab === 'vectorization_jobs'" class="flex w-full">
        <table class="text-sm border border-gray-300 w-full">
          <tr class="py-2">
            <th class="py-3 px-4 text-left font-semibold">Job Status</th>
            <th class="py-3 px-4 text-left font-semibold"># of Jobs</th>
            <th class="py-3 px-4 text-left font-semibold">Total Files Processed</th>
            <th class="py-3 px-4 text-left font-semibold">Completed Files</th>
            <th class="py-3 px-4 text-left font-semibold">Failed Files</th>
          </tr>
          <tr v-for="(item, key, index) in vectorization_jobs" class="border-t">
            <td class="py-3 px-4">{{ key }}</td>
            <td class="py-3 px-4">{{ item.total_count }}</td>
            <td class="py-3 px-4">{{ item.total_total_files }}</td>
            <td class="py-3 px-4">{{ item.total_completed_files }}</td>
            <td class="py-3 px-4">{{ item.total_failed_files }}</td>
          </tr>

        </table>

      </div>

      <div v-if="sub_tab === 'vector_stores'" class="flex w-full">
        <table class="text-sm border border-gray-300 w-full">
          <tr class="py-2">
            <th class="py-3 px-4 text-left font-semibold">Vector Store ID</th>
            <th class="py-3 px-4 text-left font-semibold">Type</th>
            <th class="py-3 px-4 text-left font-semibold">Created At</th>
          </tr>
          <tr v-for="vs in vector_stores" class="border-t">
            <td class="py-3 px-4">{{ vs.vector_store_id }}</td>
            <td class="py-3 px-4">{{ vs.store_type }}</td>
            <td class="py-3 px-4">{{ vs.created_at }}</td>
          </tr>

        </table>

      </div>

    </div>


  </div>

</template>

<script setup lang="ts">


// import { RangePickerComponent } from "@/components/RangePickerComponent.vue";

const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl

const selected = ref({ start: new Date() });

const onDateChange = (date: any) => {
  console.log(date);
};

definePageMeta({
  layout: "shell",
  middleware: "auth"
});

import { ref } from 'vue'
import { useFetch } from '#app'

const models = ref([])

const apps = ref([

])

const selectedModel = ref('')
const selectedApp = ref('')
const startDate = ref('')
const endDate = ref('')
const metrics = ref([])
const extraction_jobs = ref([])
const chunking_jobs = ref([])
const vectorization_jobs = ref([])
const vector_stores = ref([])
const is_fetched = ref(false)
const is_loading = ref(false)

const sub_tab = ref('invocations')


const setSubTab = (tab: string) => {
  sub_tab.value = tab;
}

const fetchMetrics = async () => {
 

  if (!selectedApp.value || !startDate.value || !endDate.value) {
    alert('Please fill in all fields')
    return
  }

  is_fetched.value = false;
  is_loading.value = true;
  console.log(selectedApp.value, startDate.value, endDate.value);

  // call /api/metrics/invocations POST
  const response = await fetch(BASE_URL + 'admin/metrics/invocations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({

      app_id: selectedApp.value,
      start_date: startDate.value,
      end_date: endDate.value
    })
  });

  const data = await response.json();
  console.log(data);
  var entries = [];
  // data is map of model_id -> metrics
  for (const [key, value] of Object.entries(data.items)) {
    entries.push(value);
    console.log(key, value);
  }
  metrics.value = entries;

  /////////

  const extractionjobs = await fetch(BASE_URL + 'admin/metrics/extraction-jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({

      app_id: selectedApp.value,
      start_date: startDate.value,
      end_date: endDate.value
    })
  });

  const data2 = await extractionjobs.json();
  console.log(data2);
  extraction_jobs.value = data2.items;

  const chunkingjobs = await fetch(BASE_URL + 'admin/metrics/chunking-jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({

      app_id: selectedApp.value,
      start_date: startDate.value,
      end_date: endDate.value
    })
  });

  const data3 = await chunkingjobs.json();
  console.log(data3);
  chunking_jobs.value = data3.items;


  const vectorizationjobs = await fetch(BASE_URL + 'admin/metrics/vectorization-jobs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({

      app_id: selectedApp.value,
      start_date: startDate.value,
      end_date: endDate.value
    })
  });

  const data4 = await vectorizationjobs.json();
  console.log(data4);
  vectorization_jobs.value = data4.items;

  const vectorstores = await fetch(BASE_URL + 'admin/metrics/vector-stores', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({

      app_id: selectedApp.value,
      start_date: startDate.value,
      end_date: endDate.value
    })
  });

  const data5 = await vectorstores.json();
  console.log(data5);
  vector_stores.value = data5.items;

  is_fetched.value = true;
  is_loading.value = false;
}

const fetchModels = async () => {
  //   const { data } = await useFetch('')
  //   models.value = data

  const response = await fetch(BASE_URL + 'model/list_models', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    credentials: 'include',
  });

  const data = await response.json();
  console.log(data);
  data.forEach((model: any) => {
    models.value.push({ id: model.model_id, name: model.model_name } as { id: any, name: any });
  });
}

async function get_all_app_clients() {
  await nextTick();
  useFetch(BASE_URL + 'admin/platform/get_all_app_clients', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include'
  }).then((res) => {
    console.log(res.data.value);

    res.data.value.forEach((app: any) => {
      apps.value.push({ id: app.app_id, name: app.app_name + ' - ' + app.app_id });
    });

  });


}

onMounted(() => {
  fetchModels();
  get_all_app_clients();
});


</script>

<style scoped>
.sub-tab-active {
  color: #0972D3 !important;
  border-bottom: 3px solid #0972D3;
  font-weight: 600;
}

.sub-tab {
  color: #000;
}
</style>