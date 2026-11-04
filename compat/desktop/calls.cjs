// Parse the actual pinned call expressions, including multiline/type-argument calls.
const fs = require('node:fs')
const path = require('node:path')
const [compiler, root, output] = process.argv.slice(2)
const ts = require(compiler)
const inventory = [], dto = [], routes = []
const method = /\.(get|post|response|mutate|agentRead|agentRequest|download|read)$/
function walk(dir) {
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const absolute = path.join(dir, entry.name)
    if (entry.isDirectory()) { walk(absolute); continue }
    if (!/\.tsx?$/.test(entry.name) || entry.name.endsWith('contract.gen.ts')) continue
    const file = path.relative(root, absolute).split(path.sep).join('/')
    const source = ts.createSourceFile(file, fs.readFileSync(absolute, 'utf8'), ts.ScriptTarget.Latest, true)
    if (source.parseDiagnostics.length) throw Error('invalid pinned TS: ' + file)
    const text = n => n.getText(source)
    const location = n => ({ file, line: source.getLineAndCharacterOfPosition(n.getStart()).line + 1 })
    function visit(n) {
      if (ts.isCallExpression(n)) {
        const callee = text(n.expression), args = n.arguments.map(text)
        let group
        if (/^window\.yuki(?:\.\w+)+$/.test(callee)) group = 'renderer'
        else if (file === 'src/preload/index.ts' && /^ipcRenderer\.\w+$/.test(callee)) group = 'preload'
        else if (file === 'src/main/app.ts' && ['action','ipcMain.handle','ipcMain.on'].includes(callee)) group = 'ipc'
        else if (file === 'src/main/agent-connector.ts' && /^(spawn|this\.(runner|bundled|run))$/.test(callee)) group = 'connector-cli'
        else if (file.startsWith('src/main/') && (callee === 'readStream' ||
                 method.test(callee) && /client|agents|agentRead|agentRequest|cache\.download|this\.read|modelClient/i.test(callee))) group = 'http'
        if (group) inventory.push({...location(n), group, callee, args: group === 'ipc' ? args.slice(0,1) : args,
                                    types: (n.typeArguments || []).map(text)})
      }
      if (ts.isIndexedAccessTypeNode(n) && /\['schemas'\]$/.test(text(n.objectType))) {
        dto.push({...location(n), schema: text(n.indexType).slice(1,-1), type: text(n.objectType)})
      }
      if ((ts.isStringLiteralLike(n) || ts.isTemplateExpression(n)) && file.startsWith('src/main/')) {
        let pattern = n.text
        if (ts.isTemplateExpression(n)) {
          pattern = n.head.text
          for (const span of n.templateSpans) {
            const querySuffix = ts.isConditionalExpression(span.expression) && text(span.expression).includes("'?'")
            pattern += (querySuffix ? '' : '{}') + span.literal.text
          }
        }
        routes.push({...location(n), expression: text(n), pattern})
      }
      ts.forEachChild(n, visit)
    }
    visit(source)
  }
}
walk(path.join(root, 'src'))
// Exercise the pinned, pure fingerprint helper on ordered attachment IDs.
const helperPath = path.join(root, 'src/main/outbox/fingerprint.ts')
const compiled = ts.transpileModule(fs.readFileSync(helperPath, 'utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022}
})
const helper = path.join(path.dirname(output), 'fingerprint.cjs')
fs.writeFileSync(helper, compiled.outputText)
const {payloadHash} = require(helper)
const hash = x => payloadHash('message','scope',x)
const first = hash({attachments:['one','two'], text:'雪'})
const reordered = hash({text:'雪', attachments:['one','two']})
const reversed = hash({text:'雪', attachments:['two','one']})
if (first !== reordered || first === reversed) throw Error('ordered payload fingerprint mismatch')
fs.writeFileSync(output, JSON.stringify({typescript:ts.version, inventory, dto, routes,
  fingerprint:{first,reordered,reversed}}))
