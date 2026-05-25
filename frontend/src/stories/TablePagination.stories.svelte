<script module>
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import TablePagination from "$lib/components/TablePagination.svelte";

  const { Story } = defineMeta({
    title: "Library/TablePagination",
    component: TablePagination,
    tags: ["autodocs"],
    argTypes: {},
    args: {
      maxPages: 10
    },
    decorators: [],
    render: templateSnippet
  });
</script>

{#snippet templateSnippet(args)}
  <TablePagination {...args} bind:page={args.page} />
  <p>Selected page: {args.page}</p>
{/snippet}

<Story name="Default" args={{ page: 1 }} />

<Story name="Few pages" args={{ page: 4, maxPages: 4 }} />

<Story name="Loneliest page" args={{ page: 1, maxPages: 1 }} />

<Story name="Lots of pages" args={{ page: 5, maxPages: 200 }} />

<Story name="Lots of pages, end selected" args={{ page: 196, maxPages: 200 }} />

<Story name="Lots of pages, middle selected" args={{ page: 100, maxPages: 200 }} />
