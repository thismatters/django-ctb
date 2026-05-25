<script lang="ts">
  import PureFilteredPartTable from "$lib/components/PureFilteredPartTable.svelte";
  import { partsFilterMetaRetrieve } from "$lib/api/generated";

  let queryParams = $state({});
  let partsFilterMetaPromise = $state(partsFilterMetaRetrieve());
  let filterMetaResourceState = $state({ data: null, loading: true, error: null });
  async function fetchFilterMeta() {
    filterMetaResourceState.data = await partsFilterMetaRetrieve();
  }
  fetchFilterMeta();
</script>

<PureFilteredPartTable
  {filterMetaResourceState}
  {partListResourceState}
  {maxPages}
  bind:queryParams
/>
