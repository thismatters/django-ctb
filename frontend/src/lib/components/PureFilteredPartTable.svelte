<script lang="ts">
  import TableFilterPanel from "$lib/components/TableFilterPanel.svelte";
  import PurePartTable from "$lib/components/PurePartTable.svelte";
  import TablePagination from "$lib/components/TablePagination.svelte";

  import type { FilterMeta, Part } from "$lib/api/generated";
  import type { ResourceState } from "$lib/api/useResource.svelte";

  interface Props {
    filterMetaResourceState: ResourceState<FilterMeta>;
    partListResourceState: ResourceState<Array<Part>>;
    maxPages: number;
    filterParams: Record<string, Array<string>>;
  }
  const pageLimit = 100;

  let {
    filterMetaResourceState,
    partListResourceState,
    maxPages = 1,
    queryParams = $bindable({ limit: pageLimit, offset: 0 })
  }: Props = $props();

  let filterParams: Record<string, Array<string>> = $state({});

  function search() {
    // put filterParams and pageParams together into queryParams
    queryParams = { ...filterParams };
    setPage(page);
  }

  let page = $state(1);
  function setPage(pageToBe: number) {
    queryParams = {
      ...queryParams,
      offset: (parseInt(pageToBe) - 1) * pageLimit,
      limit: pageLimit
    };
    page = pageToBe;
  }
</script>

<div class="parts-browser">
  <TableFilterPanel {...filterMetaResourceState} bind:filterParams onsearch={search} />
  <PurePartTable {...partListResourceState} />
  <TablePagination bind:page={() => page, setPage} {maxPages} />
</div>

<style>
  .parts-browser {
    width: 800px;
  }
</style>
