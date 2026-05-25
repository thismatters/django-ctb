<script lang="ts">
  import DataTable, { Body } from "@smui/data-table";
  // import LinearProgress from '@smui/linear-progress';
  // import Button from '@smui/button';

  import type { Part } from "$lib/api/generated";
  import type { ResourceState } from "$lib/api/useResource.svelte";

  const { data, loading, error }: ResourceState<Part> = $props();
</script>

<!-- TableWrapper.svelte -->
<DataTable>
  <Body>
    <slot />
    <!-- <slot /> is deprecated... switch to {@render ...} -->
  </Body>
</DataTable>
