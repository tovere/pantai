export interface UserInfo {
  homePath?: string;
  id: number;
  password: string;
  realName: string;
  roles: string[];
  username: string;
}

export interface TimezoneOption {
  offset: number;
  timezone: string;
}

export const MOCK_USERS: UserInfo[] = [
  {
    id: 0,
    password: '123456',
    realName: 'Template Admin',
    roles: ['super'],
    username: 'template-admin',
    homePath: '/workspace',
  },
  {
    id: 1,
    password: '123456',
    realName: 'Admin',
    roles: ['admin'],
    username: 'admin',
    homePath: '/workspace',
  },
  {
    id: 2,
    password: '123456',
    realName: 'Editor',
    roles: ['user'],
    username: 'editor',
    homePath: '/workspace',
  },
];

export const MOCK_CODES = [
  {
    codes: ['AC_100100', 'AC_100110', 'AC_100120', 'AC_100010'],
    username: 'template-admin',
  },
  {
    codes: ['AC_100010', 'AC_100020', 'AC_100030'],
    username: 'admin',
  },
  {
    codes: ['AC_1000001', 'AC_1000002'],
    username: 'editor',
  },
];

const dashboardMenus = [
  {
    meta: {
      order: -1,
      title: 'page.dashboard.title',
    },
    name: 'Dashboard',
    path: '/dashboard',
    redirect: '/workspace',
    children: [
      {
        name: 'Workspace',
        path: '/workspace',
        component: '/dashboard/workspace/index',
        meta: {
          affixTab: true,
          icon: 'carbon:workspace',
          title: 'page.dashboard.workspace',
        },
      },
      {
        name: 'WorkspacePersonal',
        path: '/workspace/personal',
        component: '/dashboard/workspace/personal',
        meta: {
          hideInMenu: true,
          icon: 'carbon:workspace',
          title: '个人工作台',
        },
      },
      {
        name: 'WorkspaceTeam',
        path: '/workspace/team',
        component: '/dashboard/workspace/team',
        meta: {
          icon: 'carbon:user-multiple',
          title: '团队工作台',
        },
      },
    ],
  },
];

const exampleMenus = [
  {
    name: 'TemplateExample',
    path: '/example',
    redirect: '/example/index',
    meta: {
      icon: 'carbon:template',
      order: 10,
      title: '模板示例',
    },
    children: [
      {
        name: 'TemplateExamplePage',
        path: '/example/index',
        component: '/example/index',
        meta: {
          title: '示例页面',
        },
      },
    ],
  },
];

export const MOCK_MENUS = [
  {
    menus: [...dashboardMenus, ...exampleMenus],
    username: 'template-admin',
  },
  {
    menus: [...dashboardMenus, ...exampleMenus],
    username: 'admin',
  },
  {
    menus: [...dashboardMenus, ...exampleMenus],
    username: 'editor',
  },
];

let menuId = 1;
function cloneWithIds(nodes: any[], pid = 0): any[] {
  return nodes.map((node) => {
    const id = menuId++;
    const children = Array.isArray(node.children)
      ? cloneWithIds(node.children, id)
      : undefined;
    return {
      id,
      pid,
      status: 1,
      type: children ? 'catalog' : 'menu',
      ...node,
      children,
    };
  });
}

export const MOCK_MENU_LIST = cloneWithIds([...dashboardMenus, ...exampleMenus]);

export function getMenuIds(menus: any[]) {
  const ids: number[] = [];
  menus.forEach((item) => {
    ids.push(item.id);
    if (item.children && item.children.length > 0) {
      ids.push(...getMenuIds(item.children));
    }
  });
  return ids;
}

export const TIME_ZONE_OPTIONS: TimezoneOption[] = [
  { offset: -5, timezone: 'America/New_York' },
  { offset: 0, timezone: 'Europe/London' },
  { offset: 8, timezone: 'Asia/Shanghai' },
  { offset: 9, timezone: 'Asia/Tokyo' },
  { offset: 9, timezone: 'Asia/Seoul' },
];
