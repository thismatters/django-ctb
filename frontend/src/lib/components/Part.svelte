<script lang="ts">
  import { partsRetrieve } from "$lib/api/generated";
  import { useResource } from "$lib/api/useResource.svelte";
  import { PurePart } from "$lib/components/PurePart.svelte";

  let { partId }: { partId: number } = $props();

  const partResource = $derived(
    useResource("parts", partId, () => partsRetrieve({ path: { id: partId } }))
  );
</script>

<PurePart {...partResource} />
