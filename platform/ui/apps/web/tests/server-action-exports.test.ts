import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import ts from 'typescript';
import { expect, it } from 'vitest';

const lib = resolve(process.cwd(), 'src/lib');

it('exports only async functions from use server modules', () => {
  const files = readdirSync(lib).filter((name) => name.endsWith('.ts'));
  let checked = 0;
  for (const name of files) {
    const source = ts.createSourceFile(name, readFileSync(join(lib, name), 'utf8'),
      ts.ScriptTarget.Latest, true);
    const first = source.statements[0];
    if (!first || !ts.isExpressionStatement(first) || !ts.isStringLiteral(first.expression) ||
      first.expression.text !== 'use server') continue;
    checked += 1;
    for (const statement of source.statements) {
      if ((ts.isExportDeclaration(statement) && !statement.isTypeOnly) || ts.isExportAssignment(statement)) {
        throw new Error(`${name} re-exports a runtime value from a use server module`);
      }
      if (!ts.canHaveModifiers(statement) ||
        !ts.getModifiers(statement)?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword)) continue;
      if (ts.isTypeAliasDeclaration(statement) || ts.isInterfaceDeclaration(statement)) continue;
      const isAsync = (node: ts.Node) => ts.canHaveModifiers(node) && !!ts.getModifiers(node)?.some(
        (modifier) => modifier.kind === ts.SyntaxKind.AsyncKeyword,
      );
      const valid = ts.isFunctionDeclaration(statement) && isAsync(statement) ||
        ts.isVariableStatement(statement) && statement.declarationList.declarations.every((declaration) =>
          !!declaration.initializer &&
          (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer)) &&
          isAsync(declaration.initializer));
      expect(valid, `${name} exports a runtime value that Next.js cannot use as a server action`).toBe(true);
    }
  }
  expect(checked).toBeGreaterThan(0);
});
