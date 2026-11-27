// Illustrative topology and values for the browser-only preview.
const demoCoordinates = [
  [8, 23], [22, 17], [37, 22], [52, 17], [67, 22], [82, 16], [95, 24],
  [13, 42], [28, 37], [43, 38], [59, 37], [74, 40], [86, 37], [97, 45],
  [5, 58], [20, 54], [35, 57], [50, 52], [64, 57], [79, 54], [91, 59],
  [11, 75], [25, 70], [40, 74], [55, 69], [69, 76], [84, 69], [97, 76],
  [5, 90], [19, 88], [34, 91], [48, 86], [63, 91], [78, 86], [91, 90],
];

const demoConnections = [];
for (let row = 0; row < 5; row += 1) {
  for (let column = 0; column < 7; column += 1) {
    const node = row * 7 + column + 1;
    if (column < 6) demoConnections.push([node, node + 1]);
    if (row < 4) demoConnections.push([node, node + 7]);
    if (row < 4 && column < 6 && column !== (row + 2) % 6) demoConnections.push([node, node + 8]);
  }
}
demoConnections.push([10, 17], [17, 18]);

const demoScenarios = [0.987, 0.826, 0.214].map((probability, index) => ({
  id: 'Демо-0' + (index + 1),
  probability,
  valid: probability >= .5,
  nodes: demoCoordinates.map(([x, y], position) => {
    const number = position + 1;
    const nominal = [500, 500, 220, 110, 110][Math.floor(position / 7)];
    const swing = Math.sin(number * 1.63) * .023 - index * .014;
    return {number, nominal, voltage: nominal * (1 + swing), angle: -2.1 - number * .23 + Math.cos(number) - index * 2, x, y};
  }),
  lines: demoConnections.map(([from, to], position) => {
    const current = 93 + (1 + Math.sin(position * 1.73)) * (221 + index * 46);
    return {number: position + 1, from, to, current, load: current / (720 - (position % 7) * 23) * 100};
  }),
}));
