import { defineOverridesPreferences } from '@vben/preferences';

/**
 * @description 项目配置文件
 * 只需要覆盖项目中的一部分配置，不需要的配置不用覆盖，会自动使用默认配置
 * !!! 更改配置后请清空缓存，否则可能不生效
 */
export const overridesPreferences = defineOverridesPreferences({
  // overrides
  app: {
    name: '策略盯盘台',
    defaultHomePath: '/watch/board',
  },
  copyright: {
    companyName: 'Template Company',
    companySiteLink: 'https://example.com',
  },
  logo: {
    source:
      'https://dummyimage.com/215x60/0f172a/ffffff.png&text=WEB-ELE+TEMPLATE',
  },
});
