<script module>
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import PurePartTable from "$lib/components/PurePartTable.svelte";

  import * as PurePartStories from "./PurePart.stories.svelte";

  const { Story } = defineMeta({
    title: "Library/PurePartTable",
    component: PurePartTable,
    tags: ["autodocs"],
    argTypes: {},
    args: {},
    decorators: []
  });

  export const TestData = [
    { ...PurePartStories.TestData, id: 1, description: "the worst test part", value: "1.1u" },
    { ...PurePartStories.TestData, id: 2, description: "the middest test part", value: "2.2u" },
    { ...PurePartStories.TestData, id: 3, description: "the best test part", value: "3.3u" }
  ];
</script>

<Story name="Default" args={{ data: TestData, loading: false, error: null }} />

<Story name="Error" args={{ data: TestData, loading: false, error: { message: "error state" } }} />
<Story name="Loading" args={{ data: TestData, loading: true, error: null }} />
