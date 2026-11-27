import assert from "node:assert/strict";
import test from "node:test";

import { REPLY_TEMPLATES, fillTemplate, unfilledTags, unfilledWarning } from "../../components/messages/messages-model.ts";

/** MQA-028: unfilled template tags are caught; a picked template is filled from the thread. */

test("unfilled tags are found once each, however they are spaced", () => {
  assert.deepEqual(unfilledTags("Hi {{store_name}}, on {{ platform }} - {{store_name}}"), ["{{store_name}}", "{{platform}}"]);
  assert.deepEqual(unfilledTags("Hi Rico, braces { like } these are fine"), []);
  assert.equal(unfilledWarning(["{{store_name}}", "{{platform}}"]), "Fill in {{store_name}} and {{platform}} before sending.");
  assert.equal(unfilledWarning([]), null);
});

test("a template is filled with what the thread knows, and nothing is invented", () => {
  const text = fillTemplate(REPLY_TEMPLATES[0].text, { seller_name: "Rico", store_name: "PowerHub PH", platform: "Shopee" });
  assert.match(text, /^Hi Rico, thanks for claiming PowerHub PH on Shopee\./);
  assert.deepEqual(unfilledTags(text), []);
  const partial = fillTemplate("Hi {{seller_name}} at {{store_name}}", { seller_name: "Rico", store_name: "  " });
  assert.equal(partial, "Hi Rico at {{store_name}}");
  assert.deepEqual(unfilledTags(partial), ["{{store_name}}"]);
});
