<script lang="ts">
  interface Props {
    maxPages: number;
    page: number;
  }

  let { maxPages = 10, page = $bindable(1) }: Props = $props();

  function setPage(pageToBe: number) {
    page = Math.min(Math.max(1, parseInt(pageToBe)), parseInt(maxPages));
  }

  const elipses = "...";
  const maxVisible = 9;
  let elidedPages = $derived.by(() => {
    const pages = Array.from({ length: maxPages }, (_, i) => i + 1);
    if (pages.length <= maxVisible) {
      return pages;
    }
    // Calculate how many items to show on the ends
    const edge = Math.floor((maxVisible - 1) / 3);
    const middleWidth = maxVisible - 2 * edge;
    const halfWidth = Math.ceil(middleWidth / 2);
    let middlePortion = [elipses];
    let start = pages.slice(0, edge);
    let end = pages.slice(-edge);
    if (page <= edge + halfWidth) {
      start = pages.slice(0, edge + middleWidth);
    } else if (page > maxPages - edge - halfWidth) {
      end = pages.slice(-(edge + middleWidth));
    } else {
      // create the middle portion
      const middleStart = page - halfWidth;
      middlePortion = pages.slice(middleStart, middleStart + middleWidth);
      middlePortion.push(elipses);
      middlePortion.unshift(elipses);
    }

    return [...start, ...middlePortion, ...end];
  });
</script>

<div class="elided-page-numbers">
  <span><button onclick={() => setPage(page - 1)} disabled={page <= 1}>&lt;</button></span>
  {#each elidedPages as thisPage}
    {#if thisPage === elipses}
      <span>{elipses}</span>
    {:else}
      <span><button onclick={() => setPage(thisPage)}>{thisPage}</button></span>
    {/if}
  {/each}
  <span><button onclick={() => setPage(page + 1)} disabled={page >= maxPages}>&gt;</button></span>
</div>
